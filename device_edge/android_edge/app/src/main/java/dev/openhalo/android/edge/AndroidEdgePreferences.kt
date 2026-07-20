package dev.openhalo.android.edge

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

data class AndroidEdgeConfig(
    val runtimeMode: String,
    val runtimeUrl: String,
    val deviceId: String,
    val edgeToken: String,
    val deviceCredential: String = ""
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
    private const val KEY_DEVICE_CREDENTIAL = "device_credential"
    private const val KEY_EVENT_HISTORY = "event_history"
    private const val KEY_CONVERSATION_HISTORY = "conversation_history"
    private const val KEY_BACKGROUND_KEEPALIVE = "background_keepalive"
    private const val KEY_SCREEN_CONTEXT_OBSERVATION = "screen_context_observation"
    private const val KEY_ACCESSIBILITY_OBSERVED_ENABLED = "accessibility_observed_enabled"
    private const val KEY_ACCESSIBILITY_DISABLED_NOTICE_DISMISSED =
        "accessibility_disabled_notice_dismissed"
    private const val MAX_HISTORY_ITEMS = 12
    private const val MAX_CONVERSATION_ITEMS = 40

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
                ?: edgeTokenForMode(runtimeMode),
            deviceCredential = prefs.getString(KEY_DEVICE_CREDENTIAL, "").orEmpty()
        )
    }

    fun saveConfig(context: Context, config: AndroidEdgeConfig) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_RUNTIME_MODE, config.runtimeMode)
            .putString(KEY_RUNTIME_URL, config.runtimeUrl)
            .putString(KEY_DEVICE_ID, config.deviceId)
            .putString(KEY_EDGE_TOKEN, config.edgeToken)
            .putString(KEY_DEVICE_CREDENTIAL, config.deviceCredential)
            .apply()
    }

    fun savePairedDeviceCredential(
        context: Context,
        config: AndroidEdgeConfig,
        deviceCredential: String
    ): Boolean {
        return context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_RUNTIME_MODE, config.runtimeMode)
            .putString(KEY_RUNTIME_URL, config.runtimeUrl)
            .putString(KEY_DEVICE_ID, config.deviceId)
            .putString(KEY_EDGE_TOKEN, config.edgeToken)
            .putString(KEY_DEVICE_CREDENTIAL, deviceCredential)
            .commit()
    }

    fun clearDeviceCredential(context: Context): Boolean {
        return context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .remove(KEY_DEVICE_CREDENTIAL)
            .commit()
    }

    fun backgroundKeepAliveEnabled(context: Context): Boolean {
        return context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getBoolean(KEY_BACKGROUND_KEEPALIVE, true)
    }

    fun saveBackgroundKeepAliveEnabled(context: Context, enabled: Boolean) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putBoolean(KEY_BACKGROUND_KEEPALIVE, enabled)
            .commit()
    }

    fun screenContextObservationEnabled(context: Context): Boolean {
        return context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getBoolean(KEY_SCREEN_CONTEXT_OBSERVATION, false)
    }

    fun saveScreenContextObservationEnabled(context: Context, enabled: Boolean) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putBoolean(KEY_SCREEN_CONTEXT_OBSERVATION, enabled)
            .commit()
    }

    fun markAccessibilityServiceObservedEnabled(context: Context) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putBoolean(KEY_ACCESSIBILITY_OBSERVED_ENABLED, true)
            .putBoolean(KEY_ACCESSIBILITY_DISABLED_NOTICE_DISMISSED, false)
            .commit()
    }

    fun accessibilityServiceWasObservedEnabled(context: Context): Boolean {
        return context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getBoolean(KEY_ACCESSIBILITY_OBSERVED_ENABLED, false)
    }

    fun accessibilityDisabledNoticeDismissed(context: Context): Boolean {
        return context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getBoolean(KEY_ACCESSIBILITY_DISABLED_NOTICE_DISMISSED, false)
    }

    fun dismissAccessibilityDisabledNotice(context: Context) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putBoolean(KEY_ACCESSIBILITY_DISABLED_NOTICE_DISMISSED, true)
            .commit()
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
        val next = appendBounded(
            existing = runCatching {
                JSONArray(prefs.getString(KEY_EVENT_HISTORY, "[]"))
            }.getOrDefault(JSONArray()),
            item = nextItem,
            maxItems = MAX_HISTORY_ITEMS
        )
        val edit = prefs.edit().putString(KEY_EVENT_HISTORY, next.toString())
        if (isChatTranscriptItem(title, kind)) {
            val nextConversation = appendBounded(
                existing = runCatching {
                    JSONArray(prefs.getString(KEY_CONVERSATION_HISTORY, "[]"))
                }.getOrDefault(JSONArray()),
                item = nextItem,
                maxItems = MAX_CONVERSATION_ITEMS
            )
            edit.putString(KEY_CONVERSATION_HISTORY, nextConversation.toString())
        }
        edit.apply()
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
        return parseHistoryItems(history)
    }

    fun conversationHistoryItems(context: Context): List<AndroidEdgeHistoryItem> {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val conversation = runCatching {
            JSONArray(prefs.getString(KEY_CONVERSATION_HISTORY, "[]"))
        }.getOrDefault(JSONArray())
        if (conversation.length() > 0) {
            return parseHistoryItems(conversation).filter {
                isChatTranscriptItem(it.title, it.kind)
            }
        }
        return historyItems(context).filter {
            isChatTranscriptItem(it.title, it.kind)
        }
    }

    private fun parseHistoryItems(history: JSONArray): List<AndroidEdgeHistoryItem> {
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

    fun clearHistory(context: Context) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .remove(KEY_EVENT_HISTORY)
            .remove(KEY_CONVERSATION_HISTORY)
            .apply()
    }

    private fun appendBounded(existing: JSONArray, item: JSONObject, maxItems: Int): JSONArray {
        val next = JSONArray().put(item)
        for (index in 0 until minOf(existing.length(), maxItems - 1)) {
            val existingItem = existing.optJSONObject(index)
            if (existingItem != null) {
                next.put(existingItem)
            }
        }
        return next
    }

    internal fun isChatTranscriptItem(title: String, kind: String): Boolean =
        title == "Submitted mobile.input" ||
            kind == "notification" ||
            kind == "reply"

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
