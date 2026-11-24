package ae.rasid.rootguard.core

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/** Server address, phone key and preferred language, kept in the app's private preferences. */
data class Config(val server: String, val key: String, val lang: String) {
  companion object {
    private const val P = "rasid_root"
    fun load(ctx: Context): Config {
      val p = ctx.getSharedPreferences(P, Context.MODE_PRIVATE)
      return Config(p.getString("server", "") ?: "", p.getString("key", "") ?: "", p.getString("lang", "auto") ?: "auto")
    }
    fun save(ctx: Context, server: String, key: String, lang: String) {
      ctx.getSharedPreferences(P, Context.MODE_PRIVATE).edit()
        .putString("server", server.trim()).putString("key", key.trim()).putString("lang", lang).apply()
    }
  }
}

/** History of calls RASID ended, newest first (no audio, no transcript). */
object Events {
  private const val P = "rasid_root_events"
  fun add(ctx: Context, number: String?, risk: Int, reasons: String, ended: Boolean) {
    val p = ctx.getSharedPreferences(P, Context.MODE_PRIVATE)
    val arr = try { JSONArray(p.getString("list", "[]")) } catch (_: Exception) { JSONArray() }
    val out = JSONArray().put(JSONObject().put("at", System.currentTimeMillis()).put("number", number ?: "")
      .put("risk", risk).put("reasons", reasons).put("ended", ended))
    for (i in 0 until minOf(arr.length(), 49)) out.put(arr.get(i))
    p.edit().putString("list", out.toString()).apply()
  }
  fun list(ctx: Context): String = ctx.getSharedPreferences(P, Context.MODE_PRIVATE).getString("list", "[]") ?: "[]"
}

/** Runs a command as root (Magisk su). */
object Root {
  fun run(cmd: String): Boolean = try {
    val p = ProcessBuilder("su", "-c", cmd).redirectErrorStream(true).start()
    p.waitFor(5, TimeUnit.SECONDS) && p.exitValue() == 0
  } catch (e: Exception) { false }

  fun available(): Boolean = try {
    val p = ProcessBuilder("su", "-c", "id").redirectErrorStream(true).start()
    val out = p.inputStream.bufferedReader().readText()
    p.waitFor(5, TimeUnit.SECONDS) && out.contains("uid=0")
  } catch (e: Exception) { false }
}
