package ae.rasid.rootguard.core

import android.content.Context
import android.content.Intent
import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition

class RasidRootModule : Module() {
  private val ctx: Context get() = appContext.reactContext ?: throw IllegalStateException("No context")

  override fun definition() = ModuleDefinition {
    Name("RasidRoot")

    Function("saveConfig") { server: String, key: String, lang: String -> Config.save(ctx, server, key, lang) }

    Function("getConfig") {
      val c = Config.load(ctx)
      mapOf("server" to c.server, "key" to c.key, "lang" to c.lang)
    }

    Function("arm") {
      androidx.core.content.ContextCompat.startForegroundService(ctx, Intent(ctx, RootGuardService::class.java))
      true
    }

    Function("disarm") {
      ctx.stopService(Intent(ctx, RootGuardService::class.java))
      true
    }

    Function("status") {
      val info = ctx.applicationInfo
      mapOf(
        "armed" to RootGuardService.running,
        "status" to RootGuardService.lastStatus,
        "systemApp" to ((info.flags and ApplicationInfo.FLAG_SYSTEM) != 0),
        "captureAudioOutput" to (ctx.checkSelfPermission("android.permission.CAPTURE_AUDIO_OUTPUT") == PackageManager.PERMISSION_GRANTED),
      )
    }

    AsyncFunction("checkRoot") { Root.available() }

    Function("events") { Events.list(ctx) }
  }
}
