package dev.openhalo.android.edge

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class EdgeApiFramesTest {
    @Test
    fun pairingConnectFrameUsesTheOneTimePairingAuthenticationKind() {
        val frame = buildConnectFrame(
            "android-edge-test",
            EdgeAuthentication(AUTH_KIND_PAIRING, "one-time-code")
        )

        val auth = frame.getJSONObject("auth")
        assertEquals("connect", frame.getString("type"))
        assertEquals(AUTH_KIND_PAIRING, auth.getString("kind"))
        assertEquals("one-time-code", auth.getString("token"))
    }

    @Test
    fun deviceConnectFrameUsesThePersistedDeviceAuthenticationKind() {
        val frame = buildConnectFrame(
            "android-edge-test",
            EdgeAuthentication(AUTH_KIND_DEVICE, "device-credential")
        )

        val auth = frame.getJSONObject("auth")
        assertEquals(AUTH_KIND_DEVICE, auth.getString("kind"))
        assertEquals("device-credential", auth.getString("token"))
    }

    @Test
    fun pairedDeviceCredentialParserAcceptsOnlyConnectOkDeviceCredentials() {
        val paired = JSONObject()
            .put("type", "connect_ok")
            .put(
                "auth",
                JSONObject()
                    .put("kind", AUTH_KIND_DEVICE)
                    .put("token", "device-credential")
            )

        assertEquals("device-credential", parsePairedDeviceCredential(paired))
        assertEquals(null, parsePairedDeviceCredential(JSONObject().put("type", "connect_ok")))
        assertEquals(
            null,
            parsePairedDeviceCredential(
                JSONObject()
                    .put("type", "connect_ok")
                    .put("auth", JSONObject().put("kind", AUTH_KIND_LEGACY).put("token", "shared"))
            )
        )
    }

    @Test
    fun stablePairingRequiresWssWhileDevelopmentMayUseLocalWs() {
        assertTrue(pairingTransportAllowed(RUNTIME_MODE_STABLE, "wss://runtime.example/openhalo/edge"))
        assertFalse(pairingTransportAllowed(RUNTIME_MODE_STABLE, "ws://runtime.example/openhalo/edge"))
        assertTrue(pairingTransportAllowed(RUNTIME_MODE_DEVELOPMENT, "ws://10.0.2.2:18765"))
    }

    @Test
    fun androidSessionRequiresEitherPairingCodeOrDeviceCredentialInEveryMode() {
        assertTrue(devicePairingRequired("", ""))
        assertFalse(devicePairingRequired("device-credential", ""))
        assertFalse(devicePairingRequired("", "one-time-code"))
        assertTrue(devicePairingRequired("   ", "   "))
    }

    @Test
    fun chatTranscriptKeepsDeliveredInputAndNotificationsButExcludesQueuedInput() {
        assertTrue(AndroidEdgePreferences.isChatTranscriptItem("notification.show -> ok", "notification"))
        assertTrue(AndroidEdgePreferences.isChatTranscriptItem("Submitted mobile.input", "event"))
        assertFalse(AndroidEdgePreferences.isChatTranscriptItem("Queued mobile.input", "event"))
        assertTrue(AndroidEdgePreferences.isChatTranscriptItem("Rendered runtime reply", "reply"))
    }

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
            .put("interaction_turn_id", "interaction-turn-1")
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
        assertEquals("interaction-turn-1", frame.getString("interaction_turn_id"))
        assertEquals("android-edge-test", frame.getString("device_id"))
        assertEquals("ok", result.getString("status"))
        assertEquals("notification.show", result.getString("capability"))
        assertEquals("delivered", result.getJSONObject("details").getString("message"))
    }

    @Test
    fun capabilityAnnounceRegistersScreenContextObservationProvider() {
        val frame = buildCapabilityAnnounceFrame("android-edge-test")
        val capabilities = frame.getJSONArray("capabilities")
        val screenContext = (0 until capabilities.length())
            .map { capabilities.getJSONObject(it) }
            .first { it.getString("name") == "mobile.screen_context" }
        val observations = screenContext.getJSONArray("observations")
        val screenObservation = observations.getJSONObject(0)

        assertEquals("edge_to_runtime", screenContext.getString("direction"))
        assertEquals("mobile.screen_context", screenObservation.getString("name"))
        assertEquals(
            "object",
            screenObservation.getJSONObject("schema").getString("type")
        )
    }

    @Test
    fun notificationShowCapabilityUsesCanonicalPayloadContract() {
        val frame = buildCapabilityAnnounceFrame("android-edge-test")
        val notification = (0 until frame.getJSONArray("capabilities").length())
            .map { frame.getJSONArray("capabilities").getJSONObject(it) }
            .first { it.getString("name") == "notification.show" }
        val schema = notification.getJSONObject("input_schema")
        val required = schema.getJSONArray("required")
        val properties = schema.getJSONObject("properties")

        assertEquals("body", required.getString(0))
        assertTrue(schema.getBoolean("additionalProperties").not())
        assertEquals("string", properties.getJSONObject("title").getString("type"))
        assertEquals("string", properties.getJSONObject("body").getString("type"))
        assertEquals(1, properties.getJSONObject("body").getInt("minLength"))
        assertEquals("medium", notification.getString("interruptiveness"))
        assertEquals("user_visible", notification.getString("side_effect"))
    }

    @Test
    fun notificationShowPayloadRequiresBodyAndDefaultsOptionalTitle() {
        val explicit = parseNotificationShowPayload(
            JSONObject().put("title", "Runtime status").put("body", "Running")
        )
        val defaulted = parseNotificationShowPayload(JSONObject().put("body", "Running"))

        assertEquals(NotificationShowPayload("Runtime status", "Running"), explicit)
        assertEquals(NotificationShowPayload(DEFAULT_NOTIFICATION_TITLE, "Running"), defaulted)
        assertEquals(null, parseNotificationShowPayload(JSONObject().put("message", "legacy")))
        assertEquals(null, parseNotificationShowPayload(JSONObject().put("body", "  ")))
    }

    @Test
    fun replyRenderCapabilityUsesCanonicalBodyContract() {
        val frame = buildCapabilityAnnounceFrame("android-edge-test")
        val replyRender = (0 until frame.getJSONArray("capabilities").length())
            .map { frame.getJSONArray("capabilities").getJSONObject(it) }
            .first { it.getString("name") == "mobile.reply.render" }
        val schema = replyRender.getJSONObject("input_schema")
        val properties = schema.getJSONObject("properties")

        assertEquals("body", schema.getJSONArray("required").getString(0))
        assertTrue(schema.getBoolean("additionalProperties").not())
        assertEquals("string", properties.getJSONObject("body").getString("type"))
        assertEquals(1, properties.getJSONObject("body").getInt("minLength"))
    }

    @Test
    fun capabilityAnnounceRegistersInteractionProgressPresentation() {
        val frame = buildCapabilityAnnounceFrame("android-edge-test")
        val progress = (0 until frame.getJSONArray("capabilities").length())
            .map { frame.getJSONArray("capabilities").getJSONObject(it) }
            .first { it.getString("name") == INTERACTION_PROGRESS_CAPABILITY }

        assertEquals("runtime_to_edge", progress.getString("direction"))
        assertEquals("interaction_status", progress.getString("kind"))
        assertTrue(
            progress.getJSONArray("affordances").toString()
                .contains("render_interaction_progress")
        )
    }

    @Test
    fun interactionProgressParserAcceptsOnlyTheSafePublicContract() {
        val frame = JSONObject()
            .put("type", "interaction_progress")
            .put("device_id", "android-edge-test")
            .put(
                "progress",
                JSONObject()
                    .put("version", 1)
                    .put("interaction_id", "interaction-1")
                    .put("interaction_turn_id", "turn-1")
                    .put("sequence", 2)
                    .put("phase", "planning")
                    .put("state", "active")
                    .put("occurred_at", "2026-07-19T14:00:00Z")
                    .put("presentation_hint", "working")
            )

        val parsed = parseInteractionProgressFrame(frame, "android-edge-test")

        assertEquals("interaction-1", parsed?.interactionId)
        assertEquals("turn-1", parsed?.interactionTurnId)
        assertEquals(2, parsed?.sequence)
        assertEquals("planning", parsed?.phase)

        frame.getJSONObject("progress").put("provider", "private-provider")
        assertEquals(null, parseInteractionProgressFrame(frame, "android-edge-test"))
        frame.getJSONObject("progress").remove("provider")
        assertEquals(null, parseInteractionProgressFrame(frame, "another-device"))
    }

    @Test
    fun interactionProgressReducerOrdersUpdatesAndClearsSettledInteractions() {
        val first = InteractionProgress(
            interactionId = "interaction-1",
            interactionTurnId = "turn-1",
            sequence = 1,
            phase = "deliberating",
            state = "active",
            occurredAt = "2026-07-19T14:00:00Z",
            presentationHint = "working"
        )
        val active = reduceInteractionProgress(InteractionProgressState(), first)
        val stale = reduceInteractionProgress(active, first.copy(phase = "planning"))
        val settled = reduceInteractionProgress(
            active,
            first.copy(
                sequence = 2,
                phase = "completed",
                state = "settled",
                presentationHint = "completed"
            )
        )

        assertEquals(active, stale)
        assertEquals("deliberating", active.activeProgresses.single().phase)
        assertTrue(settled.activeProgresses.isEmpty())
        assertEquals(2, settled.latestSequenceByInteraction["interaction-1"])
        assertEquals(settled, reduceInteractionProgress(settled, first))
        assertTrue(clearInteractionProgress(active).activeProgresses.isEmpty())
    }

    @Test
    fun renderedReplyUsesBodyInsteadOfSerializingItsPayload() {
        assertEquals(
            "Hello from runtime",
            parseRenderedReplyBody(JSONObject().put("body", "Hello from runtime"))
        )
        assertEquals(
            "Legacy reply",
            parseRenderedReplyBody(JSONObject().put("message", "Legacy reply"))
        )
        assertEquals(null, parseRenderedReplyBody(JSONObject()))
    }

    @Test
    fun globalChatAutoScrollsOnlyForNewMessagesWhenReaderIsAtBottom() {
        assertTrue(shouldAutoScrollGlobalChat(0, 1, userWasAtBottom = true))
        assertTrue(shouldAutoScrollGlobalChat(4, 5, userWasAtBottom = true))
        assertFalse(shouldAutoScrollGlobalChat(4, 5, userWasAtBottom = false))
        assertFalse(shouldAutoScrollGlobalChat(4, 4, userWasAtBottom = true))
        assertTrue(isChatAtBottom(120, 120))
        assertFalse(isChatAtBottom(119, 120))
    }

    @Test
    fun screenContextObservationRedactsSensitiveNodesAndNeverUploadsScreenshot() {
        val observation = buildScreenContextObservation(
            ScreenContextCapture(
                trigger = "accessibility_event",
                eventKind = "view_text_changed",
                packageName = "com.example.chat",
                rootClassName = "ChatActivity",
                appVisibility = "background",
                serviceState = "foreground",
                accessibilityState = "enabled",
                screenState = "unlocked",
                queueDepth = 0,
                eventsCoalesced = 3,
                eventsDropped = 1,
                captureThrottled = false,
                nodes = listOf(
                    ScreenContextNode(
                        className = "android.widget.EditText",
                        text = "password 123456",
                        bounds = listOf(0, 100, 500, 180),
                        editable = true,
                        password = true,
                        focused = true
                    ),
                    ScreenContextNode(
                        className = "android.widget.Button",
                        text = "Send",
                        bounds = listOf(500, 100, 620, 180),
                        clickable = true
                    )
                )
            ),
            observedAt = "2026-07-05T14:24:53Z"
        )
        val value = observation.getJSONObject("value")

        assertEquals("mobile.screen_context", observation.getString("name"))
        assertEquals(false, value.getBoolean("raw_screenshot_uploaded"))
        assertEquals("blocked", value.getString("sensitivity"))
        assertEquals("health_only", value.getString("capture_mode"))
        assertEquals("", value.getString("visible_text_summary"))
        assertEquals(0, value.getJSONArray("interactive_elements").length())
    }

    @Test
    fun screenContextObservationIndexesInteractiveElementsWhenNormal() {
        val observation = buildScreenContextObservation(
            ScreenContextCapture(
                trigger = "accessibility_event",
                eventKind = "view_clicked",
                packageName = "com.example.messaging",
                rootClassName = "ChatActivity",
                appVisibility = "background",
                serviceState = "foreground",
                accessibilityState = "enabled",
                screenState = "unlocked",
                queueDepth = 0,
                eventsCoalesced = 2,
                eventsDropped = 0,
                captureThrottled = false,
                nodes = listOf(
                    ScreenContextNode(text = "Message list", scrollable = true),
                    ScreenContextNode(text = "Reply", editable = true),
                    ScreenContextNode(text = "Send", clickable = true)
                )
            )
        )
        val value = observation.getJSONObject("value")

        assertEquals("normal", value.getString("sensitivity"))
        assertEquals("accessibility_tree", value.getString("capture_mode"))
        assertEquals("com.example.messaging", value.getString("package_name"))
        assertEquals("ChatActivity", value.getString("root_class_name"))
        assertTrue(value.getString("visible_text_summary").contains("Message list"))
        assertEquals(3, value.getJSONArray("interactive_elements").length())
        assertEquals("text_input", value.getJSONArray("interactive_elements").getJSONObject(1).getString("role"))
    }

    @Test
    fun screenContextCapabilitySchemaIncludesAppIdentityFields() {
        val frame = buildCapabilityAnnounceFrame("android-edge-test")
        val capabilities = frame.getJSONArray("capabilities")
        val screenContext = (0 until capabilities.length())
            .map { capabilities.getJSONObject(it) }
            .first { it.getString("name") == "mobile.screen_context" }
        val screenObservation = screenContext
            .getJSONArray("observations")
            .getJSONObject(0)
        val schema = screenObservation.getJSONObject("schema")
        val required = schema.getJSONArray("required")
        val properties = schema.getJSONObject("properties")
        val requiredNames = (0 until required.length()).map { required.getString(it) }

        assertTrue(requiredNames.contains("package_name"))
        assertTrue(requiredNames.contains("root_class_name"))
        assertEquals("string", properties.getJSONObject("package_name").getString("type"))
        assertEquals("string", properties.getJSONObject("root_class_name").getString("type"))
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

    @Test
    fun backgroundObservationHeartbeatUsesBoundedSteadyStateInterval() {
        assertEquals(60_000L, backgroundObservationIntervalMillis())
    }

    @Test
    fun backgroundPermissionGuidanceCallsOutKnownManufacturerRestrictions() {
        assertEquals(
            "ready for foreground-service background observation",
            AndroidEdgeHealth.backgroundPermissionGuidance(
                manufacturer = "Google",
                batteryState = "unrestricted"
            )
        )
        assertTrue(
            AndroidEdgeHealth.backgroundPermissionGuidance(
                manufacturer = "Xiaomi",
                batteryState = "may restrict background"
            ).contains("Autostart")
        )
        assertTrue(
            AndroidEdgeHealth.backgroundPermissionGuidance(
                manufacturer = "Samsung",
                batteryState = "may restrict background"
            ).contains("Sleeping apps")
        )
    }
}
