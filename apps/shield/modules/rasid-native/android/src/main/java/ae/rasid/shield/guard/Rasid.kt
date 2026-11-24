package ae.rasid.shield.guard

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import org.json.JSONArray
import org.json.JSONObject
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

/** Shared config, cache and HTTP helpers for the notification listener and the call screening service. */
object Rasid {
  private const val PREFS = "rasid_native"
  const val CHANNEL_ALERTS = "alerts"
  const val CHANNEL_EMERGENCY = "emergency"

  fun prefs(ctx: Context) = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

  fun configure(ctx: Context, server: String, deviceId: String, token: String, lang: String) {
    prefs(ctx).edit().putString("server", server.trimEnd('/')).putString("device_id", deviceId)
      .putString("token", token).putString("lang", lang).apply()
  }

  fun configured(ctx: Context) = !prefs(ctx).getString("server", "").isNullOrEmpty() && !prefs(ctx).getString("token", "").isNullOrEmpty()

  /** E.164 digits, UAE local numbers get 971 (mirrors rasid/phones.py e164). */
  fun e164(raw: String?): String {
    if (raw.isNullOrBlank()) return ""
    val s = raw.trim()
    val d = s.filter { it.isDigit() }
    if (d.isEmpty()) return ""
    return when {
      s.startsWith("+") -> d
      d.startsWith("00") -> d.substring(2)
      d.startsWith("971") -> d
      d.startsWith("0") -> "971" + d.substring(1)
      Regex("^(5\\d{8}|[2-9]\\d{7})$").matches(d) -> "971$d"
      else -> d
    }
  }

  fun sha256(s: String): String =
    MessageDigest.getInstance("SHA-256").digest(s.toByteArray()).joinToString("") { "%02x".format(it) }

  /** Local cache of known numbers: hash -> {status, org, reports}. Filled from /api/v1/sync/numbers via JS. */
  fun setCache(ctx: Context, json: String) = prefs(ctx).edit().putString("cache", json).apply()

  fun cached(ctx: Context, number: String): JSONObject? {
    val raw = prefs(ctx).getString("cache", null) ?: return null
    return try {
      val arr = JSONArray(raw)
      val h = sha256(e164(number))
      (0 until arr.length()).map { arr.getJSONObject(it) }.firstOrNull { it.optString("hash") == h }
    } catch (e: Exception) { null }
  }

  fun http(ctx: Context, method: String, path: String, body: JSONObject?, timeoutMs: Int): JSONObject? {
    val p = prefs(ctx)
    val server = p.getString("server", "") ?: return null
    if (server.isEmpty()) return null
    return try {
      val c = URL(server + path).openConnection() as HttpURLConnection
      c.requestMethod = method
      c.connectTimeout = timeoutMs
      c.readTimeout = timeoutMs
      c.setRequestProperty("Content-Type", "application/json")
      c.setRequestProperty("X-Device-Id", p.getString("device_id", ""))
      c.setRequestProperty("X-Device-Token", p.getString("token", ""))
      if (body != null) {
        c.doOutput = true
        OutputStreamWriter(c.outputStream).use { it.write(body.toString()) }
      }
      if (c.responseCode !in 200..299) return null
      JSONObject(c.inputStream.bufferedReader().readText())
    } catch (e: Exception) { null }
  }

  fun ensureChannels(ctx: Context) {
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
    val nm = ctx.getSystemService(NotificationManager::class.java)
    if (nm.getNotificationChannel(CHANNEL_ALERTS) == null)
      nm.createNotificationChannel(NotificationChannel(CHANNEL_ALERTS, "Scam warnings", NotificationManager.IMPORTANCE_HIGH))
    if (nm.getNotificationChannel(CHANNEL_EMERGENCY) == null)
      nm.createNotificationChannel(NotificationChannel(CHANNEL_EMERGENCY, "Emergency scam alerts", NotificationManager.IMPORTANCE_HIGH).apply {
        enableVibration(true); vibrationPattern = longArrayOf(0, 600, 200, 600, 200, 600); setBypassDnd(true)
      })
  }

  fun warn(ctx: Context, title: String, text: String, emergency: Boolean = false, deepLink: String = "rasidshield://") {
    ensureChannels(ctx)
    val launch = Intent(Intent.ACTION_VIEW, android.net.Uri.parse(deepLink)).apply {
      setPackage(ctx.packageName); addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    }
    val pi = PendingIntent.getActivity(ctx, text.hashCode(), launch, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
    val n = NotificationCompat.Builder(ctx, if (emergency) CHANNEL_EMERGENCY else CHANNEL_ALERTS)
      .setSmallIcon(android.R.drawable.stat_sys_warning)
      .setContentTitle(title)
      .setContentText(text)
      .setStyle(NotificationCompat.BigTextStyle().bigText(text))
      .setPriority(NotificationCompat.PRIORITY_MAX)
      .setCategory(if (emergency) NotificationCompat.CATEGORY_ALARM else NotificationCompat.CATEGORY_MESSAGE)
      .setAutoCancel(true)
      .setContentIntent(pi)
      .apply { if (emergency) setFullScreenIntent(pi, true) }
      .build()
    try {
      ctx.getSystemService(NotificationManager::class.java).notify(text.hashCode(), n)
    } catch (e: SecurityException) { /* POST_NOTIFICATIONS not granted */ }
  }

  /** Short warning in the user's language (same texts as the JS side, src/lib/i18n.ts). */
  fun scamText(ctx: Context): String = when (prefs(ctx).getString("lang", "en")) {
    "ar" -> "تحذير: قد يكون هذا احتيالاً. لا تدفع ولا تشارك أي رمز."
    "hi" -> "चेतावनी: यह धोखाधड़ी हो सकती है। पैसे न भेजें और कोड साझा न करें।"
    "ur" -> "انتباہ: یہ فراڈ ہو سکتا ہے۔ رقم نہ بھیجیں اور کوڈ شیئر نہ کریں۔"
    "ml" -> "മുന്നറിയിപ്പ്: ഇത് തട്ടിപ്പാകാം. പണം അയക്കരുത്, കോഡ് പങ്കിടരുത്."
    "ta" -> "எச்சரிக்கை: இது மோசடியாக இருக்கலாம். பணம் அனுப்பாதீர்கள், குறியீட்டைப் பகிராதீர்கள்."
    "si" -> "අවවාදයයි: මෙය වංචාවක් විය හැක. මුදල් යවන්න එපා, කේත බෙදාගන්න එපා."
    "tl" -> "Babala: Posibleng scam ito. Huwag magbayad o magbigay ng code."
    "bn" -> "সতর্কতা: এটি প্রতারণা হতে পারে। টাকা পাঠাবেন না এবং কোড শেয়ার করবেন না।"
    "ne" -> "चेतावनी: यो ठगी हुन सक्छ। पैसा नपठाउनुहोस् र कोड साझा नगर्नुहोस्।"
    "ru" -> "Внимание: это может быть мошенничество. Не платите и не сообщайте коды."
    "zh" -> "警告：这可能是诈骗。不要付款，也不要分享验证码。"
    else -> "Warning: this may be a scam. Do not pay and do not share any code."
  }
}
