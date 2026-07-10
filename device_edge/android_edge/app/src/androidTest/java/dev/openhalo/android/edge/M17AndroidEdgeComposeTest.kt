package dev.openhalo.android.edge

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertHasClickAction
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.performTextReplacement
import androidx.compose.ui.semantics.SemanticsActions
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

@RunWith(AndroidJUnit4::class)
class M17AndroidEdgeComposeTest {
    @get:Rule
    val composeRule = createAndroidComposeRule<MainActivity>()

    @Before
    fun resetSharedState() {
        val appContext = InstrumentationRegistry.getInstrumentation().targetContext
        appContext.getSharedPreferences("openhalo_android_edge", android.content.Context.MODE_PRIVATE)
            .edit()
            .clear()
            .commit()
        EdgeDiagnosticsStore.update(EdgeDiagnostics())
    }

    @Test
    fun launchesConnectWithStableStatusAndProductNavigation() {
        composeRule.onNodeWithText("OpenHalo").assertIsDisplayed()
        composeRule.onNodeWithTag(AndroidEdgeTestTags.CONNECT_TAB).assertIsDisplayed()
        composeRule.onNodeWithTag(AndroidEdgeTestTags.GLOBAL_CHAT_TAB).assertIsDisplayed()
        composeRule.onNodeWithTag(AndroidEdgeTestTags.SETTINGS_TAB).assertIsDisplayed()
        assertTrue(composeRule.onAllNodesWithText("Diagnostics").fetchSemanticsNodes().isEmpty())
        composeRule.onNodeWithTag(AndroidEdgeTestTags.STATUS_CONNECTION).assertIsDisplayed()
        composeRule.onNodeWithTag(AndroidEdgeTestTags.STATUS_SERVICE).assertIsDisplayed()
        composeRule.onNodeWithTag(AndroidEdgeTestTags.STATUS_RECONNECT).assertIsDisplayed()
        composeRule.onNodeWithTag(AndroidEdgeTestTags.CONNECT_PRIMARY_ACTION)
            .assertIsDisplayed()
    }

    @Test
    fun globalChatCommandEnablesSendWithoutUsingAdbTextScraping() {
        composeRule.onNodeWithTag(AndroidEdgeTestTags.GLOBAL_CHAT_TAB).performClick()

        composeRule.onNodeWithTag(AndroidEdgeTestTags.GLOBAL_CHAT_INPUT)
            .performTextInput("hello runtime")

        composeRule.onNodeWithTag(AndroidEdgeTestTags.GLOBAL_CHAT_SEND)
            .assertIsEnabled()
    }

    @Test
    fun globalChatSendStartsExistingSubmitTextServicePath() {
        composeRule.onNodeWithTag(AndroidEdgeTestTags.GLOBAL_CHAT_TAB).performClick()
        composeRule.onNodeWithTag(AndroidEdgeTestTags.GLOBAL_CHAT_INPUT)
            .performTextInput("hello runtime")

        composeRule.onNodeWithTag(AndroidEdgeTestTags.GLOBAL_CHAT_SEND)
            .performClick()

        composeRule.onNodeWithTag(AndroidEdgeTestTags.GLOBAL_CHAT_SEND)
            .assertIsNotEnabled()
    }

    @Test
    fun topLevelNavigationUsesStableComposeTags() {
        composeRule.onNodeWithTag(AndroidEdgeTestTags.GLOBAL_CHAT_TAB).performClick()
        composeRule.onNodeWithTag(AndroidEdgeTestTags.GLOBAL_CHAT_LIST).assertIsDisplayed()

        composeRule.onNodeWithTag(AndroidEdgeTestTags.SETTINGS_TAB).performClick()
        composeRule.onNodeWithTag(AndroidEdgeTestTags.SETTINGS_RUNTIME_URL)
            .performScrollTo()
            .assertIsDisplayed()
        composeRule.onNodeWithTag(AndroidEdgeTestTags.SETTINGS_DEVICE_NAME)
            .performScrollTo()
            .assertIsDisplayed()

        composeRule.onNodeWithTag(AndroidEdgeTestTags.CONNECT_TAB).performClick()
        composeRule.onNodeWithTag(AndroidEdgeTestTags.CONNECT_PRIMARY_ACTION).assertIsDisplayed()
    }

    @Test
    fun settingsRuntimeUrlAndDeviceNameEditThroughVisibleRows() {
        val appContext = InstrumentationRegistry.getInstrumentation().targetContext

        composeRule.onNodeWithTag(AndroidEdgeTestTags.SETTINGS_TAB).performClick()
        composeRule.onNodeWithTag(AndroidEdgeTestTags.SETTINGS_RUNTIME_URL)
            .performScrollTo()
            .performClick()
        composeRule.onNodeWithTag(AndroidEdgeTestTags.SETTINGS_RUNTIME_URL_EDITOR)
            .performTextReplacement("ws://runtime.local:18765/openhalo/edge")
        composeRule.onNodeWithTag(AndroidEdgeTestTags.SETTINGS_EDIT_SAVE).performClick()
        composeRule.waitForIdle()

        assertEquals(
            "ws://runtime.local:18765/openhalo/edge",
            AndroidEdgePreferences.loadConfig(appContext).runtimeUrl
        )

        composeRule.onNodeWithTag(AndroidEdgeTestTags.SETTINGS_DEVICE_NAME)
            .performScrollTo()
            .performClick()
        composeRule.onNodeWithTag(AndroidEdgeTestTags.SETTINGS_DEVICE_NAME_EDITOR)
            .performTextReplacement("daily phone")
        composeRule.onNodeWithTag(AndroidEdgeTestTags.SETTINGS_EDIT_SAVE).performClick()
        composeRule.waitForIdle()

        assertEquals("daily phone", AndroidEdgePreferences.loadConfig(appContext).deviceId)
    }

    @Test
    fun settingsRowsExposeAccurateActionsForPermissionsAndKeepalive() {
        val appContext = InstrumentationRegistry.getInstrumentation().targetContext

        composeRule.onNodeWithTag(AndroidEdgeTestTags.SETTINGS_TAB).performClick()

        composeRule.onNodeWithTag(AndroidEdgeTestTags.SETTINGS_PROTOCOL_ROW)
            .performScrollTo()
            .assertHasNoClickAction()
        composeRule.onNodeWithTag(AndroidEdgeTestTags.SETTINGS_LOCAL_NETWORK_ROW)
            .performScrollTo()
            .assertHasNoClickAction()
        composeRule.onNodeWithTag(AndroidEdgeTestTags.SETTINGS_NOTIFICATION_ROW)
            .performScrollTo()
            .assertHasClickAction()
        composeRule.onNodeWithTag(AndroidEdgeTestTags.SETTINGS_BATTERY_ROW)
            .performScrollTo()
            .assertHasClickAction()

        assertTrue(AndroidEdgePreferences.backgroundKeepAliveEnabled(appContext))
        composeRule.onNodeWithTag(AndroidEdgeTestTags.SETTINGS_KEEPALIVE_ROW)
            .performScrollTo()
            .performClick()
        composeRule.waitForIdle()
        assertFalse(AndroidEdgePreferences.backgroundKeepAliveEnabled(appContext))

        assertFalse(AndroidEdgePreferences.screenContextObservationEnabled(appContext))
        composeRule.onNodeWithTag(AndroidEdgeTestTags.SETTINGS_SCREEN_CONTEXT_ROW)
            .performScrollTo()
            .performClick()
        composeRule.waitForIdle()
        assertTrue(AndroidEdgePreferences.screenContextObservationEnabled(appContext))
        composeRule.onNodeWithTag(AndroidEdgeTestTags.SETTINGS_ACCESSIBILITY_ROW)
            .performScrollTo()
            .assertHasClickAction()
    }

    @Test
    fun screenContextObservationPreferenceSurvivesActivityRecreate() {
        val appContext = InstrumentationRegistry.getInstrumentation().targetContext

        composeRule.onNodeWithTag(AndroidEdgeTestTags.SETTINGS_TAB).performClick()
        composeRule.onNodeWithTag(AndroidEdgeTestTags.SETTINGS_SCREEN_CONTEXT_ROW)
            .performScrollTo()
            .performClick()
        composeRule.waitForIdle()

        assertTrue(AndroidEdgePreferences.screenContextObservationEnabled(appContext))

        composeRule.activityRule.scenario.recreate()
        composeRule.waitForIdle()

        assertTrue(AndroidEdgePreferences.screenContextObservationEnabled(appContext))
        composeRule.onNodeWithTag(AndroidEdgeTestTags.SETTINGS_TAB).performClick()
        composeRule.onNodeWithTag(AndroidEdgeTestTags.SETTINGS_SCREEN_CONTEXT_ROW)
            .performScrollTo()
            .assertIsDisplayed()
    }

    @Test
    fun globalChatProjectsNotificationHistoryAsConversationActivity() {
        val appContext = InstrumentationRegistry.getInstrumentation().targetContext
        AndroidEdgePreferences.appendHistory(
            appContext,
            title = "notification.show -> ok",
            body = "Hello from runtime",
            kind = "notification"
        )

        composeRule.onNodeWithTag(AndroidEdgeTestTags.GLOBAL_CHAT_TAB).performClick()

        assertTrue(
            composeRule.onAllNodesWithText("notification.show -> ok", substring = true)
                .fetchSemanticsNodes()
                .isNotEmpty()
        )
        assertTrue(
            composeRule.onAllNodesWithText("Hello from runtime", substring = true)
                .fetchSemanticsNodes()
            .isNotEmpty()
        )
    }

    @Test
    fun globalChatAutoScrollsToNewestPhoneMessageAndShowsClockTime() {
        val appContext = InstrumentationRegistry.getInstrumentation().targetContext
        val formatter = DateTimeFormatter.ofPattern("HH:mm").withZone(ZoneId.systemDefault())
        val beforeAppend = Instant.now()
        repeat(14) { index ->
            AndroidEdgePreferences.appendHistory(
                appContext,
                title = "mobile.input -> accepted",
                body = "auto-scroll-message-$index",
                kind = "event"
            )
        }
        val expectedTimes = setOf(formatter.format(beforeAppend), formatter.format(Instant.now()))

        composeRule.onNodeWithTag(AndroidEdgeTestTags.GLOBAL_CHAT_TAB).performClick()
        composeRule.waitForIdle()

        composeRule.onNodeWithText("auto-scroll-message-13").assertIsDisplayed()
        assertTrue(
            expectedTimes.any { expectedTime ->
                composeRule.onAllNodesWithText("iPhone · $expectedTime", substring = true)
                    .fetchSemanticsNodes()
                    .isNotEmpty()
            }
        )
    }

    @Test
    fun appContextAndAndroidHealthHelpersAreAvailable() {
        val appContext = InstrumentationRegistry.getInstrumentation().targetContext

        assertEquals("dev.openhalo.android.edge", appContext.packageName)
        assertTrue(AndroidEdgeHealth.fullScreenAlertState(appContext).isNotBlank())
        assertTrue(AndroidEdgeHealth.batteryOptimizationState(appContext).isNotBlank())
    }

    @Test
    fun accessibilitySettingsListParserAcceptsFullAndShortComponentNames() {
        val packageName = "dev.openhalo.android.edge"
        val className = "dev.openhalo.android.edge.OpenHaloAccessibilityService"

        assertTrue(
            accessibilityServiceEnabledInSettingsList(
                enabledServices = "$packageName/$className",
                packageName = packageName,
                className = className
            )
        )
        assertTrue(
            accessibilityServiceEnabledInSettingsList(
                enabledServices = "$packageName/.OpenHaloAccessibilityService",
                packageName = packageName,
                className = className
            )
        )
        assertFalse(
            accessibilityServiceEnabledInSettingsList(
                enabledServices = "other.package/.OtherAccessibilityService",
                packageName = packageName,
                className = className
            )
        )
    }

    @Test
    fun accessibilityDisabledNoticeRequiresPriorEnabledObservationAndActiveScreenContext() {
        assertTrue(
            shouldShowAccessibilityDisabledNotice(
                screenContextObservation = true,
                accessibilityServiceState = "disabled",
                accessibilityWasObservedEnabled = true,
                noticeDismissed = false
            )
        )
        assertFalse(
            shouldShowAccessibilityDisabledNotice(
                screenContextObservation = false,
                accessibilityServiceState = "disabled",
                accessibilityWasObservedEnabled = true,
                noticeDismissed = false
            )
        )
        assertFalse(
            shouldShowAccessibilityDisabledNotice(
                screenContextObservation = true,
                accessibilityServiceState = "enabled",
                accessibilityWasObservedEnabled = true,
                noticeDismissed = false
            )
        )
        assertFalse(
            shouldShowAccessibilityDisabledNotice(
                screenContextObservation = true,
                accessibilityServiceState = "disabled",
                accessibilityWasObservedEnabled = false,
                noticeDismissed = false
            )
        )
        assertFalse(
            shouldShowAccessibilityDisabledNotice(
                screenContextObservation = true,
                accessibilityServiceState = "disabled",
                accessibilityWasObservedEnabled = true,
                noticeDismissed = true
            )
        )
    }

    @Test
    fun configPersistsRuntimeIdentityAndSecretConfiguredState() {
        val appContext = InstrumentationRegistry.getInstrumentation().targetContext
        val expected = AndroidEdgeConfig(
            runtimeMode = RUNTIME_MODE_DEVELOPMENT,
            runtimeUrl = "ws://10.0.2.2:18765",
            deviceId = "android-edge-test",
            edgeToken = "test-token"
        )

        AndroidEdgePreferences.saveConfig(appContext, expected)
        val actual = AndroidEdgePreferences.loadConfig(appContext)

        assertEquals(expected, actual)
    }

    @Test
    fun historyIsNewestFirstAndBounded() {
        val appContext = InstrumentationRegistry.getInstrumentation().targetContext

        repeat(14) { index ->
            AndroidEdgePreferences.appendHistory(
                appContext,
                title = "event-$index",
                body = "body-$index",
                kind = "event"
            )
        }

        val items = AndroidEdgePreferences.historyItems(appContext)
        assertEquals(12, items.size)
        assertEquals("event-13", items.first().title)
        assertEquals("body-13", items.first().body)
        assertFalse(items.any { it.title == "event-0" })
        assertFalse(items.any { it.title == "event-1" })
    }

    @Test
    fun serviceIntentBuildersPreserveActionsAndTextPayload() {
        val appContext = InstrumentationRegistry.getInstrumentation().targetContext
        val start = AndroidEdgeService.startIntent(
            appContext,
            runtimeMode = RUNTIME_MODE_DEVELOPMENT,
            runtimeUrl = "ws://10.0.2.2:18765",
            deviceId = "android-edge-test",
            edgeToken = "test-token"
        )
        val submit = AndroidEdgeService.submitTextIntent(appContext, "hello runtime")
        val observations = AndroidEdgeService.sendObservationsIntent(appContext)
        val stop = AndroidEdgeService.stopIntent(appContext)

        assertEquals(AndroidEdgeService.ACTION_START, start.action)
        assertEquals(RUNTIME_MODE_DEVELOPMENT, start.getStringExtra(AndroidEdgeService.EXTRA_RUNTIME_MODE))
        assertEquals("ws://10.0.2.2:18765", start.getStringExtra(AndroidEdgeService.EXTRA_RUNTIME_URL))
        assertEquals("android-edge-test", start.getStringExtra(AndroidEdgeService.EXTRA_DEVICE_ID))
        assertEquals("test-token", start.getStringExtra(AndroidEdgeService.EXTRA_EDGE_TOKEN))
        assertEquals(AndroidEdgeService.ACTION_SUBMIT_TEXT, submit.action)
        assertEquals("hello runtime", submit.getStringExtra(AndroidEdgeService.EXTRA_TEXT_COMMAND))
        assertEquals(AndroidEdgeService.ACTION_SEND_OBSERVATIONS, observations.action)
        assertEquals(AndroidEdgeService.ACTION_STOP, stop.action)
    }

    @Test
    fun diagnosticsViewReflectsUpdatedEdgeDiagnosticsState() {
        composeRule.activity.runOnUiThread {
            EdgeDiagnosticsStore.update(
                EdgeDiagnostics(
                    runtimeMode = RUNTIME_MODE_DEVELOPMENT,
                    runtimeUrl = "ws://10.0.2.2:18765",
                    deviceId = "android-edge-test",
                    serviceState = "foreground",
                    connectionState = "connected",
                    lastError = "synthetic test error",
                    lastSentFrame = "{\"type\":\"event_push\",\"capability\":\"mobile.input\"}",
                    lastReceivedFrame = "{\"type\":\"action_request\",\"capability\":\"notification.show\"}",
                    recentObservations = "Sent mobile.context at test-time",
                    recentActions = "notification.show -> ok at test-time",
                    reconnectStatus = "connected",
                    backgroundObservationState = "heartbeat uploaded",
                    lastLocalObservationAt = "2026-07-09T15:00:00Z",
                    lastSuccessfulUploadAt = "2026-07-09T15:00:01Z",
                    deliveryQueueDepth = 0
                )
            )
        }

        composeRule.onNodeWithTag(AndroidEdgeTestTags.SETTINGS_TAB).performClick()
        repeat(7) {
            composeRule.onNodeWithTag(AndroidEdgeTestTags.SETTINGS_BUILD_ROW).performClick()
        }
        composeRule.onNodeWithTag(AndroidEdgeTestTags.DEVELOPER_DIAGNOSTICS_ROW).performClick()
        composeRule.waitForIdle()

        composeRule.onNodeWithTag(AndroidEdgeTestTags.DEVELOPER_DIAGNOSTICS_VIEW).assertIsDisplayed()
        composeRule.onNodeWithText("Connection\nconnected", substring = true)
            .performScrollTo()
            .assertIsDisplayed()
        composeRule.onNodeWithText("Service\nforeground", substring = true)
            .performScrollTo()
            .assertIsDisplayed()
        composeRule.onNodeWithText("synthetic test error", substring = true)
            .performScrollTo()
            .assertIsDisplayed()
        composeRule.onNodeWithText("Sent mobile.context at test-time", substring = true)
            .performScrollTo()
            .assertIsDisplayed()
        composeRule.onNodeWithText("notification.show -> ok at test-time", substring = true)
            .performScrollTo()
            .assertIsDisplayed()
        composeRule.onNodeWithText("background_observation=heartbeat uploaded", substring = true)
            .performScrollTo()
            .assertIsDisplayed()
        composeRule.onNodeWithText("last_successful_upload=2026-07-09T15:00:01Z", substring = true)
            .performScrollTo()
            .assertIsDisplayed()
    }

    @Test
    fun settingsBuildRowUnlocksDeveloperDiagnosticsEntry() {
        composeRule.onNodeWithTag(AndroidEdgeTestTags.SETTINGS_TAB).performClick()
        repeat(7) {
            composeRule.onNodeWithTag(AndroidEdgeTestTags.SETTINGS_BUILD_ROW).performClick()
        }
        composeRule.onNodeWithTag(AndroidEdgeTestTags.DEVELOPER_DIAGNOSTICS_ROW)
            .assertIsDisplayed()
    }
}

private fun androidx.compose.ui.test.SemanticsNodeInteraction.assertHasNoClickAction() {
    assertFalse(fetchSemanticsNode().config.contains(SemanticsActions.OnClick))
}
