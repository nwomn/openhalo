package dev.openhalo.android.edge

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextInput
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

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
    fun launchesDailyHomeWithStableStatusAndCommandSurfaces() {
        composeRule.onNodeWithText("OpenHalo Android Edge").assertIsDisplayed()
        composeRule.onNodeWithTag(AndroidEdgeTestTags.STATUS_CONNECTION).assertIsDisplayed()
        composeRule.onNodeWithTag(AndroidEdgeTestTags.STATUS_SERVICE).assertIsDisplayed()
        composeRule.onNodeWithTag(AndroidEdgeTestTags.STATUS_RECONNECT).assertIsDisplayed()
        composeRule.onNodeWithTag(AndroidEdgeTestTags.START).assertIsDisplayed()
        composeRule.onNodeWithTag(AndroidEdgeTestTags.STOP).assertIsDisplayed()
        composeRule.onNodeWithTag(AndroidEdgeTestTags.COMMAND_INPUT)
            .performScrollTo()
            .assertIsDisplayed()
        composeRule.onNodeWithTag(AndroidEdgeTestTags.COMMAND_SEND)
            .performScrollTo()
            .assertIsNotEnabled()
    }

    @Test
    fun textCommandEnablesSendWithoutUsingAdbTextScraping() {
        composeRule.onNodeWithTag(AndroidEdgeTestTags.COMMAND_INPUT)
            .performScrollTo()
            .performTextInput("hello runtime")

        composeRule.onNodeWithTag(AndroidEdgeTestTags.COMMAND_SEND)
            .performScrollTo()
            .assertIsEnabled()
    }

    @Test
    fun topLevelNavigationUsesStableComposeTags() {
        composeRule.onNodeWithTag(AndroidEdgeTestTags.NOTIFICATIONS_TAB).performClick()
        composeRule.onNodeWithText("Notification History").assertIsDisplayed()
        composeRule.onNodeWithTag(AndroidEdgeTestTags.NOTIFICATION_HISTORY).assertIsDisplayed()

        composeRule.onNodeWithTag(AndroidEdgeTestTags.DIAGNOSTICS_TAB).performClick()
        composeRule.onNodeWithTag(AndroidEdgeTestTags.DIAGNOSTICS_VIEW).assertIsDisplayed()
        composeRule.onNodeWithText("Connection Settings").assertIsDisplayed()

        composeRule.onNodeWithTag(AndroidEdgeTestTags.HOME_TAB).performClick()
        composeRule.onNodeWithTag(AndroidEdgeTestTags.COMMAND_INPUT)
            .performScrollTo()
            .assertIsDisplayed()
    }

    @Test
    fun appContextAndAndroidHealthHelpersAreAvailable() {
        val appContext = InstrumentationRegistry.getInstrumentation().targetContext

        assertEquals("dev.openhalo.android.edge", appContext.packageName)
        assertTrue(AndroidEdgeHealth.fullScreenAlertState(appContext).isNotBlank())
        assertTrue(AndroidEdgeHealth.batteryOptimizationState(appContext).isNotBlank())
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
    fun notificationHistoryShowsDetailFromPersistedEvents() {
        val appContext = InstrumentationRegistry.getInstrumentation().targetContext
        AndroidEdgePreferences.appendHistory(
            appContext,
            title = "notification.show -> ok",
            body = "Hello from runtime",
            kind = "notification"
        )

        composeRule.onNodeWithTag(AndroidEdgeTestTags.NOTIFICATIONS_TAB).performClick()

        assertTrue(
            composeRule.onAllNodesWithText("notification.show -> ok", substring = true)
                .fetchSemanticsNodes()
                .isNotEmpty()
        )
        composeRule.onNodeWithTag(AndroidEdgeTestTags.NOTIFICATION_DETAIL).assertIsDisplayed()
        assertTrue(
            composeRule.onAllNodesWithText("Hello from runtime", substring = true)
                .fetchSemanticsNodes()
                .isNotEmpty()
        )
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
                    reconnectStatus = "connected"
                )
            )
        }

        composeRule.onNodeWithTag(AndroidEdgeTestTags.DIAGNOSTICS_TAB).performClick()
        composeRule.waitForIdle()

        composeRule.onNodeWithText("Connection Settings").assertIsDisplayed()
        composeRule.onNodeWithText("connected").assertIsDisplayed()
        composeRule.onNodeWithText("foreground").assertIsDisplayed()
        composeRule.onNodeWithText("synthetic test error", substring = true)
            .performScrollTo()
            .assertIsDisplayed()
        composeRule.onNodeWithText("Sent mobile.context at test-time", substring = true)
            .performScrollTo()
            .assertIsDisplayed()
        composeRule.onNodeWithText("notification.show -> ok at test-time", substring = true)
            .performScrollTo()
            .assertIsDisplayed()
    }
}
