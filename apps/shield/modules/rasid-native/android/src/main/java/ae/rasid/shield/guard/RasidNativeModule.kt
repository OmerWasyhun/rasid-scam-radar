package ae.rasid.shield.guard

import android.app.Activity
import android.app.role.RoleManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.os.Build
import android.provider.Settings
import android.telecom.TelecomManager
import expo.modules.kotlin.Promise
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition

private const val ROLE_REQUEST = 4711

class RasidNativeModule : Module() {
  private var pendingRole: Promise? = null
  private val ctx: Context get() = appContext.reactContext ?: throw IllegalStateException("No context")

  override fun definition() = ModuleDefinition {
    Name("RasidNative")

    Function("configure") { server: String, deviceId: String, token: String, lang: String ->
      Rasid.configure(ctx, server, deviceId, token, lang)
    }

    Function("setNumberCache") { json: String -> Rasid.setCache(ctx, json) }

    Function("isNotificationAccessGranted") {
      val flat = Settings.Secure.getString(ctx.contentResolver, "enabled_notification_listeners") ?: ""
      val me = ComponentName(ctx, RasidNotificationListener::class.java).flattenToString()
      flat.split(":").any { it == me }
    }

    Function("openNotificationAccessSettings") {
      val i = Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
      ctx.startActivity(i)
    }

    Function("isCallScreeningRoleHeld") {
      if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
        ctx.getSystemService(RoleManager::class.java).isRoleHeld(RoleManager.ROLE_CALL_SCREENING)
      } else false
    }

    AsyncFunction("requestCallScreeningRole") { promise: Promise ->
      val activity = appContext.currentActivity
      if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q || activity == null) { promise.resolve(false); return@AsyncFunction }
      val rm = activity.getSystemService(RoleManager::class.java)
      if (rm.isRoleHeld(RoleManager.ROLE_CALL_SCREENING)) { promise.resolve(true); return@AsyncFunction }
      pendingRole = promise
      activity.startActivityForResult(rm.createRequestRoleIntent(RoleManager.ROLE_CALL_SCREENING), ROLE_REQUEST)
    }

    OnActivityResult { _, payload ->
      if (payload.requestCode == ROLE_REQUEST) {
        pendingRole?.resolve(payload.resultCode == Activity.RESULT_OK)
        pendingRole = null
      }
    }

    // Deprecated since Android 10 but still honoured on many devices when ANSWER_PHONE_CALLS is granted.
    Function("endCall") {
      try {
        @Suppress("DEPRECATION")
        ctx.getSystemService(TelecomManager::class.java).endCall()
      } catch (e: SecurityException) { false } catch (e: Exception) { false }
    }

    Function("lastIncomingNumber") { Rasid.prefs(ctx).getString("last_incoming", null) }
  }
}
