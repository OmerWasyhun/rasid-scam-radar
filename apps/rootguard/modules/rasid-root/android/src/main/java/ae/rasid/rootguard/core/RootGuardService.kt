package ae.rasid.rootguard.core

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.ServiceInfo
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Build
import android.os.IBinder
import android.telecom.TelecomManager
import android.telephony.TelephonyManager
import android.util.Log
import androidx.core.app.NotificationCompat
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString.Companion.toByteString
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * Armed Guardian. Watches the phone state; while a call is active it records the call audio (VOICE_CALL source,
 * needs the privileged CAPTURE_AUDIO_OUTPUT permission = system priv-app via the Magisk module) and streams it to the
 * RASID server. When the server says "hangup", the call is ended and a notification explains why.
 * Audio is never written to disk.
 */
class RootGuardService : Service() {
  companion object {
    const val TAG = "RasidRootGuard"
    const val CH_STATUS = "rasid_status"
    const val CH_ALERT = "rasid_alert"
    const val NOTIF_ID = 4711
    @Volatile var running = false
    @Volatile var lastStatus = "Not armed"
  }

  private val http = OkHttpClient.Builder().pingInterval(15, TimeUnit.SECONDS).build()
  private var ws: WebSocket? = null
  private var recorder: AudioRecord? = null
  private var recThread: Thread? = null
  @Volatile private var inCall = false
  private var lastNumber: String? = null

  private val phoneReceiver = object : BroadcastReceiver() {
    override fun onReceive(ctx: Context, intent: Intent) {
      val state = intent.getStringExtra(TelephonyManager.EXTRA_STATE) ?: return
      @Suppress("DEPRECATION")
      intent.getStringExtra(TelephonyManager.EXTRA_INCOMING_NUMBER)?.let { if (it.isNotBlank()) lastNumber = it }
      when (state) {
        TelephonyManager.EXTRA_STATE_OFFHOOK -> if (!inCall) startCall()
        TelephonyManager.EXTRA_STATE_IDLE -> if (inCall) endCall("call ended")
      }
    }
  }

  override fun onBind(intent: Intent?): IBinder? = null

  override fun onCreate() {
    super.onCreate()
    channels()
    val n = status("Armed: waiting for a call")
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
      startForeground(NOTIF_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE)
    } else {
      startForeground(NOTIF_ID, n)
    }
    val f = IntentFilter(TelephonyManager.ACTION_PHONE_STATE_CHANGED)
    if (Build.VERSION.SDK_INT >= 33) registerReceiver(phoneReceiver, f, Context.RECEIVER_EXPORTED) else registerReceiver(phoneReceiver, f)
    running = true
  }

  override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int = START_STICKY

  override fun onDestroy() {
    running = false
    lastStatus = "Not armed"
    try { unregisterReceiver(phoneReceiver) } catch (_: Exception) {}
    stopAudio()
    ws?.close(1000, "disarmed")
    super.onDestroy()
  }

  // ---------- call lifecycle ----------
  private fun startCall() {
    inCall = true
    val cfg = Config.load(this)
    if (cfg.server.isBlank() || cfg.key.isBlank()) { status("No server configured"); return }
    val url = cfg.server.trimEnd('/').replaceFirst("http", "ws") + "/phone/stream?key=" + cfg.key
    status("Call started: connecting to RASID…")
    ws = http.newWebSocket(Request.Builder().url(url).build(), object : WebSocketListener() {
      override fun onOpen(webSocket: WebSocket, response: Response) {
        val rate = startAudio(webSocket)
        if (rate == 0) {
          status("Couldn't capture call audio (is the Magisk module installed?)")
          webSocket.close(1000, "no audio")
          return
        }
        webSocket.send(JSONObject().put("type", "start").put("caller", lastNumber ?: "").put("rate", rate).put("lang", cfg.lang).toString())
        status("Listening to the call")
      }
      override fun onMessage(webSocket: WebSocket, text: String) = onServer(JSONObject(text))
      override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
        Log.w(TAG, "stream failed", t)
        if (inCall) status("RASID server not reachable: ${t.message?.take(60)}")
      }
    })
  }

  private fun endCall(reason: String) {
    inCall = false
    stopAudio()
    ws?.let { it.send(JSONObject().put("type", "end").toString()); it.close(1000, reason) }
    ws = null
    lastNumber = null
    status("Armed: waiting for a call")
  }

  private fun onServer(m: JSONObject) {
    when (m.optString("type")) {
      "state" -> status("Listening · risk ${m.optInt("risk")}/100 · ${m.optString("verdict")}")
      "hangup" -> {
        val flags = m.optJSONArray("flags") ?: JSONArray()
        val reasons = (0 until flags.length()).joinToString("\n") { "• " + flags.getString(it) }
        val ended = hangUp()
        Events.add(this, lastNumber, m.optInt("risk"), reasons, ended)
        alert(
          if (ended) "🚨 RASID ended a scam call" else "🚨 Scam call: hang up now",
          "Risk ${m.optInt("risk")}/100${lastNumber?.let { " · $it" } ?: ""}\n$reasons\nNever share codes or card details.\nلا تشارك أي رمز أو بيانات بطاقة."
        )
        endCall("scam")
      }
    }
  }

  // ---------- audio ----------
  /** Returns the sample rate in use, or 0 if no call-audio source works on this phone. */
  private fun startAudio(socket: WebSocket): Int {
    val sources = intArrayOf(MediaRecorder.AudioSource.VOICE_CALL, MediaRecorder.AudioSource.VOICE_DOWNLINK)
    for (src in sources) for (rate in intArrayOf(16000, 8000)) {
      val min = AudioRecord.getMinBufferSize(rate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
      if (min <= 0) continue
      val rec = newRecorder(src, rate, min) ?: continue
      try { rec.startRecording() } catch (e: Exception) { rec.release(); continue }
      recorder = rec
      Log.i(TAG, "capturing source=$src rate=$rate")
      recThread = Thread {
        val buf = ByteArray(rate / 5 * 2) // 200 ms frames
        while (inCall && recorder === rec) {
          val n = rec.read(buf, 0, buf.size)
          if (n > 0) socket.send(buf.toByteString(0, n))
        }
      }.apply { name = "rasid-call-audio"; start() }
      return rate
    }
    return 0
  }

  @Suppress("MissingPermission")
  private fun newRecorder(src: Int, rate: Int, min: Int): AudioRecord? = try {
    val r = AudioRecord(src, rate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, maxOf(min, rate))
    if (r.state == AudioRecord.STATE_INITIALIZED) r else { r.release(); null }
  } catch (e: Exception) { null }

  private fun stopAudio() {
    val r = recorder
    recorder = null
    try { r?.stop() } catch (_: Exception) {}
    r?.release()
    recThread = null
  }

  // ---------- hang up ----------
  @Suppress("DEPRECATION", "MissingPermission")
  private fun hangUp(): Boolean {
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
      try {
        val tm = getSystemService(TelecomManager::class.java)
        if (tm.endCall()) return true
      } catch (e: Exception) { Log.w(TAG, "endCall failed", e) }
    }
    return Root.run("input keyevent KEYCODE_ENDCALL")  // root fallback
  }

  // ---------- notifications ----------
  private fun channels() {
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
    val nm = getSystemService(NotificationManager::class.java)
    nm.createNotificationChannel(NotificationChannel(CH_STATUS, "Guardian status", NotificationManager.IMPORTANCE_LOW))
    nm.createNotificationChannel(NotificationChannel(CH_ALERT, "Scam calls ended", NotificationManager.IMPORTANCE_HIGH).apply {
      enableVibration(true); vibrationPattern = longArrayOf(0, 500, 200, 500, 200, 500)
    })
  }

  private fun openApp(): PendingIntent? = packageManager.getLaunchIntentForPackage(packageName)?.let {
    PendingIntent.getActivity(this, 0, it, PendingIntent.FLAG_IMMUTABLE)
  }

  private fun status(text: String): Notification {
    lastStatus = text
    val n = NotificationCompat.Builder(this, CH_STATUS)
      .setSmallIcon(android.R.drawable.ic_lock_idle_lock)
      .setContentTitle("RASID Guardian")
      .setContentText(text)
      .setOngoing(true)
      .setContentIntent(openApp())
      .build()
    if (running) getSystemService(NotificationManager::class.java).notify(NOTIF_ID, n)
    return n
  }

  private fun alert(title: String, text: String) {
    val n = NotificationCompat.Builder(this, CH_ALERT)
      .setSmallIcon(android.R.drawable.stat_sys_warning)
      .setContentTitle(title)
      .setContentText(text.lineSequence().first())
      .setStyle(NotificationCompat.BigTextStyle().bigText(text))
      .setPriority(NotificationCompat.PRIORITY_MAX)
      .setCategory(NotificationCompat.CATEGORY_ALARM)
      .setAutoCancel(true)
      .setContentIntent(openApp())
      .build()
    try { getSystemService(NotificationManager::class.java).notify((System.currentTimeMillis() % 100000).toInt(), n) } catch (_: SecurityException) {}
  }
}
