package dev.openhalo.android.edge

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

data class AndroidEdgeConfig(
    val runtimeMode: String,
    val runtimeUrl: String,
    val deviceId: String,
    val edgeToken: String
)

data class AndroidEdgeHistoryItem(
    val observedAt: String,
    val title: String,
    val body: String,
    val kind: String
)

object AndroidEdgePreferences {
    private const val PREFS_NAME = "openhalo_android_edge"
    private const val KEY_RUNTIME_MODE = "runtime_mode"
    private const val KEY_RUNTIME_URL = "runtime_url"
    private const val KEY_DEVICE_ID = "device_id"
    private const val KEY_EDGE_TOKEN = "edge_token"
    private const val KEY_EVENT_HISTORY = "event_history"
    private const val MAX_HISTORY_ITEMS = 12

    fun loadConfig(context: Context): AndroidEdgeConfig {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val runtimeMode = prefs.getString(KEY_RUNTIME_MODE, RUNTIME_MODE_STABLE)
            ?: RUNTIME_MODE_STABLE
        return AndroidEdgeConfig(
            runtimeMode = runtimeMode,
            runtimeUrl = prefs.getString(KEY_RUNTIME_URL, runtimeUrlForMode(runtimeMode))
                ?: runtimeUrlForMode(runtimeMode),
            deviceId = prefs.getString(KEY_DEVICE_ID, newDeviceId()) ?: newDeviceId(),
            edgeToken = prefs.getString(KEY_EDGE_TOKEN, edgeTokenForMode(runtimeMode))
                ?: edgeTokenForMode(runtimeMode)
        )
    }

    fun saveConfig(context: Context, config: AndroidEdgeConfig) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_RUNTIME_MODE, config.runtimeMode)
            .putString(KEY_RUNTIME_URL, config.runtimeUrl)
            .putString(KEY_DEVICE_ID, config.deviceId)
            .putString(KEY_EDGE_TOKEN, config.edgeToken)
            .apply()
    }

    fun appendHistory(
        context: Context,
        title: String,
        body: String = "",
        kind: String = "event"
    ): String {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val nextItem = JSONObject()
            .put("observed_at", nowIso())
            .put("title", title)
            .put("body", body)
            .put("kind", kind)
        val existing = runCatching {
            JSONArray(prefs.getString(KEY_EVENT_HISTORY, "[]"))
        }.getOrDefault(JSONArray())
        val next = JSONArray().put(nextItem)
        for (index in 0 until minOf(existing.length(), MAX_HISTORY_ITEMS - 1)) {
            val existingItem = existing.optJSONObject(index)
            if (existingItem != null) {
                next.put(existingItem)
            }
        }
        prefs.edit().putString(KEY_EVENT_HISTORY, next.toString()).apply()
        return formatHistory(next)
    }

    fun formattedHistory(context: Context): String {
        return historyItems(context).joinToString("\n") { item ->
            val suffix = if (item.body.isBlank()) "" else " - ${item.body}"
            "${item.observedAt} ${item.title}$suffix"
        }
    }

    fun historyItems(context: Context): List<AndroidEdgeHistoryItem> {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val history = runCatching {
            JSONArray(prefs.getString(KEY_EVENT_HISTORY, "[]"))
        }.getOrDefault(JSONArray())
        val items = mutableListOf<AndroidEdgeHistoryItem>()
        for (index in 0 until history.length()) {
            val item = history.optJSONObject(index) ?: continue
            items += AndroidEdgeHistoryItem(
                observedAt = item.optString("observed_at"),
                title = item.optString("title"),
                body = item.optString("body"),
                kind = item.optString("kind", "event")
            )
        }
        return items
    }

    fun formattedNotificationHistory(context: Context): String {
        return historyItems(context)
            .filter { it.kind == "notification" || it.kind == "reply" }
            .joinToString("\n\n") { item ->
                "${item.observedAt}\n${item.title}\n${item.body.ifBlank { "No detail" }}"
            }
    }

    private fun formatHistory(history: JSONArray): String {
        val lines = mutableListOf<String>()
        for (index in 0 until history.length()) {
            val item = history.optJSONObject(index) ?: continue
            val body = item.optString("body")
            val suffix = if (body.isBlank()) "" else " - $body"
            lines += "${item.optString("observed_at")} ${item.optString("title")}$suffix"
        }
        return lines.joinToString("\n")
    }

    private fun newDeviceId(): String =
        "android-edge-${UUID.randomUUID().toString().take(8)}"
}
