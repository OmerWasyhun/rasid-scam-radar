package ae.rasid.shield.guard

import android.app.Notification
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import org.json.JSONObject
import java.util.concurrent.Executors

/**
 * Reads incoming notifications. Only messages that contain a link, a phone number or scam wording are sent to
 * RASID; everything else stays on the phone. Runs natively, so it works while the JS app is asleep.
 */
class RasidNotificationListener : NotificationListenerService() {
  private val pool = Executors.newSingleThreadExecutor()
  private val recent = LinkedHashSet<Int>()

  private val urlRe = Regex("(https?://|www\\.)\\S+|\\b[a-z0-9-]+(\\.[a-z0-9-]+)*\\.(com|net|org|ae|top|xyz|shop|online|info|live|vip|cc|site|link|click|app|me|co)\\b", RegexOption.IGNORE_CASE)
  private val phoneRe = Regex("(\\+|00)?\\d[\\d\\s-]{7,15}\\d")
  private val lureRe = Regex("otp|verify|blocked|suspended|refund|prize|won|congratulations|customs fee|redeliver|visa|fine|مخالف|تحديث|حظر|جائزة|ویزا|वीज़ा|विसा|വിസ|விசா|වීසා", RegexOption.IGNORE_CASE)

  override fun onNotificationPosted(sbn: StatusBarNotification) {
    if (sbn.packageName == packageName || !Rasid.configured(this)) return
    val extras = sbn.notification.extras
    val title = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString() ?: ""
    val text = (extras.getCharSequence(Notification.EXTRA_BIG_TEXT) ?: extras.getCharSequence(Notification.EXTRA_TEXT))?.toString() ?: ""
    if (text.length < 8) return
    if (!urlRe.containsMatchIn(text) && !phoneRe.containsMatchIn(text) && !lureRe.containsMatchIn(text)) return
    val key = (sbn.packageName + title + text).hashCode()
    synchronized(recent) {
      if (!recent.add(key)) return
      if (recent.size > 200) recent.remove(recent.first())
    }
    pool.execute { check(sbn.packageName, title, text) }
  }

  private fun check(app: String, sender: String, text: String) {
    val body = JSONObject().put("text", text.take(5000)).put("sender", sender).put("app", app)
    val res = Rasid.http(this, "POST", "/api/v1/check/message", body, 25000) ?: return
    val verdict = res.optString("verdict")
    if (verdict != "scam" && verdict != "suspicious") return
    val reasons = res.optJSONArray("reasons")
    val why = if (reasons != null && reasons.length() > 0) reasons.getString(0) else ""
    val title = if (verdict == "scam") "RASID: scam message from $sender" else "RASID: suspicious message from $sender"
    Rasid.warn(this, title, "${Rasid.scamText(this)}\n$why", emergency = false, deepLink = "rasidshield://history")
  }
}
