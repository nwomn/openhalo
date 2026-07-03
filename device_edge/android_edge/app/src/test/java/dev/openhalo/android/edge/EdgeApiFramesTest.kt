package dev.openhalo.android.edge

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class EdgeApiFramesTest {
    @Test
    fun mobileInputFrameUsesPublicEdgeApiEventShape() {
        val frame = buildMobileInputEventFrame("android-edge-test", "hello runtime")
        val payload = frame.getJSONObject("payload")

        assertEquals(EDGE_API_VERSION, frame.getString("api_version"))
        assertEquals("event_push", frame.getString("type"))
        assertEquals("android-edge-test", frame.getString("device_id"))
        assertEquals("mobile.input", frame.getString("capability"))
        assertEquals("hello runtime", payload.getString("text"))
        assertEquals("android_edge", payload.getString("input_surface"))
        assertTrue(payload.getString("observed_at").isNotBlank())
    }

    @Test
    fun actionResultFramePreservesRequestAndInteractionLineage() {
        val request = JSONObject()
            .put("request_id", "request-1")
            .put("interaction_id", "interaction-1")
        val details = JSONObject().put("message", "delivered")

        val frame = buildActionResultFrame(
            actionRequest = request,
            deviceId = "android-edge-test",
            capability = "notification.show",
            status = "ok",
            details = details
        )
        val result = frame.getJSONObject("result")

        assertEquals(EDGE_API_VERSION, frame.getString("api_version"))
        assertEquals("action_result", frame.getString("type"))
        assertEquals("request-1", frame.getString("request_id"))
        assertEquals("interaction-1", frame.getString("interaction_id"))
        assertEquals("android-edge-test", frame.getString("device_id"))
        assertEquals("ok", result.getString("status"))
        assertEquals("notification.show", result.getString("capability"))
        assertEquals("delivered", result.getJSONObject("details").getString("message"))
    }

    @Test
    fun reconnectDelayIsBoundedBackoffPolicy() {
        assertEquals(2_000L, reconnectDelayMillis(0))
        assertEquals(2_000L, reconnectDelayMillis(1))
        assertEquals(5_000L, reconnectDelayMillis(2))
        assertEquals(10_000L, reconnectDelayMillis(3))
        assertEquals(20_000L, reconnectDelayMillis(4))
        assertEquals(30_000L, reconnectDelayMillis(5))
        assertEquals(30_000L, reconnectDelayMillis(99))
    }
}
