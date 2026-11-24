package ae.rasid.shield.guard

import android.net.Uri
import android.os.Build
import android.telecom.Call
import android.telecom.CallScreeningService
import org.json.JSONObject
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/**
 * Checks each incoming call before it rings (Android 10+, call-screening role).
 * Known scam numbers are rejected; unknown numbers ring normally with a "who is calling?" prompt.
 * The system only waits a few seconds, so the local cache answers first and the network check is capped.
 */
class RasidCallScreeningService : CallScreeningService() {
  private val pool = Executors.newCachedThreadPool()

  override fun onScreenCall(details: Call.Details) {
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q && details.callDirection != Call.Details.DIRECTION_INCOMING) {
      respondToCall(details, CallResponse.Builder().build()); return
    }
    val handle: Uri? = details.handle
    val number = handle?.schemeSpecificPart ?: ""
    Rasid.prefs(this).edit().putString("last_incoming", number).apply()

    var status = Rasid.cached(this, number)?.optString("status")
    var org = Rasid.cached(this, number)?.optString("org")
    var reports = Rasid.cached(this, number)?.optInt("reports") ?: 0
    if (status == null && Rasid.configured(this) && number.isNotEmpty()) {
      val f = pool.submit<JSONObject?> { Rasid.http(this, "POST", "/api/v1/check/number", JSONObject().put("number", number), 2500) }
      val r = try { f.get(3, TimeUnit.SECONDS) } catch (e: Exception) { null }
      status = r?.optString("verdict")
      org = r?.optString("org")
      reports = r?.optInt("reports") ?: 0
    }

    val b = CallResponse.Builder()
    when (status) {
      "scam" -> {
        b.setDisallowCall(true).setRejectCall(true).setSkipCallLog(false).setSkipNotification(false)
        Rasid.warn(this, "RASID blocked a scam call", "$number was reported as a scam by $reports people. ${Rasid.scamText(this)}", emergency = false, deepLink = "rasidshield://calls")
      }
      "reported" -> {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) b.setSilenceCall(true)
        Rasid.warn(this, "Caution: reported number calling", "$number was reported by $reports people. If you answer, never share codes or card details.", emergency = false, deepLink = "rasidshield://claim")
      }
      "official" -> {
        Rasid.warn(this, "Verified caller", "$number is an official ${org ?: ""} number.", emergency = false, deepLink = "rasidshield://calls")
      }
      else -> {
        Rasid.warn(this, "Unknown number: $number", "If they say they are from a bank, the police or a company, tap to check them.", emergency = false, deepLink = "rasidshield://claim")
      }
    }
    respondToCall(details, b.build())
  }
}
