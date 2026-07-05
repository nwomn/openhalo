package dev.openhalo.android.edge

import org.json.JSONObject

object ScreenContextObservationBridge {
    @Volatile
    private var sender: ((JSONObject) -> Unit)? = null

    fun attach(sender: (JSONObject) -> Unit) {
        this.sender = sender
    }

    fun detach() {
        sender = null
    }

    fun send(observation: JSONObject): Boolean {
        val current = sender ?: return false
        current(observation)
        return true
    }
}
