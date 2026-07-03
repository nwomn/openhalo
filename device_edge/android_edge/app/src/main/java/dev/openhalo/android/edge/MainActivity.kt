package dev.openhalo.android.edge

import android.Manifest
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.compose.ui.text.input.PasswordVisualTransformation
import dev.openhalo.android.edge.ui.theme.OpenHaloAndroidEdgeTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val initialView = intent.getStringExtra(EXTRA_INITIAL_VIEW) ?: "Home"
        setContent {
            OpenHaloAndroidEdgeTheme {
                Scaffold(modifier = Modifier.fillMaxSize()) { innerPadding ->
                    M17BootstrapScreen(
                        initialView = initialView,
                        modifier = Modifier.padding(innerPadding)
                    )
                }
            }
        }
    }

    companion object {
        const val EXTRA_INITIAL_VIEW = "dev.openhalo.android.edge.extra.INITIAL_VIEW"
        const val VIEW_NOTIFICATIONS = "Notifications"
    }
}

object AndroidEdgeTestTags {
    const val HOME_TAB = "openhalo.home.tab"
    const val NOTIFICATIONS_TAB = "openhalo.notifications.tab"
    const val DIAGNOSTICS_TAB = "openhalo.diagnostics.tab"
    const val START = "openhalo.start"
    const val STOP = "openhalo.stop"
    const val COMMAND_INPUT = "openhalo.command.input"
    const val COMMAND_SEND = "openhalo.command.send"
    const val STATUS_CONNECTION = "openhalo.status.connection"
    const val STATUS_SERVICE = "openhalo.status.service"
    const val STATUS_RECONNECT = "openhalo.status.reconnect"
    const val NOTIFICATION_HISTORY = "openhalo.notification.history"
    const val NOTIFICATION_DETAIL = "openhalo.notification.detail"
    const val DIAGNOSTICS_VIEW = "openhalo.diagnostics.view"
}

@Composable
fun M17BootstrapScreen(
    initialView: String = "Home",
    modifier: Modifier = Modifier
) {
    val context = LocalContext.current
    val appContext = context.applicationContext
    val storedConfig = remember { AndroidEdgePreferences.loadConfig(appContext) }
    var diagnostics by remember { mutableStateOf(EdgeDiagnosticsStore.current()) }
    var useStableRuntime by remember {
        mutableStateOf(storedConfig.runtimeMode == RUNTIME_MODE_STABLE)
    }
    var runtimeUrl by remember { mutableStateOf(storedConfig.runtimeUrl) }
    var deviceId by remember { mutableStateOf(storedConfig.deviceId) }
    var edgeToken by remember { mutableStateOf(storedConfig.edgeToken) }
    var textCommand by remember { mutableStateOf("") }
    var selectedView by remember { mutableStateOf(initialView) }
    var selectedNotificationIndex by remember { mutableStateOf(0) }
    val runtimeMode = if (useStableRuntime) RUNTIME_MODE_STABLE else RUNTIME_MODE_DEVELOPMENT
    val notificationItems = AndroidEdgePreferences.historyItems(appContext)
        .filter { it.kind == "notification" || it.kind == "reply" }
    val notificationPermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) {
        startEdgeService(appContext, AndroidEdgeService.sendObservationsIntent(appContext))
    }

    DisposableEffect(Unit) {
        val unsubscribe = EdgeDiagnosticsStore.subscribe { next ->
            (context as? ComponentActivity)?.runOnUiThread {
                diagnostics = next
            } ?: run {
                diagnostics = next
            }
        }
        onDispose {
            unsubscribe()
        }
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 24.dp, vertical = 32.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Text(
            text = "OpenHalo Android Edge",
            style = MaterialTheme.typography.headlineMedium
        )
        Text(
            text = "Daily mobile presence surface",
            style = MaterialTheme.typography.bodyLarge
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf("Home", "Notifications", "Diagnostics").forEach { view ->
                val tag = when (view) {
                    "Notifications" -> AndroidEdgeTestTags.NOTIFICATIONS_TAB
                    "Diagnostics" -> AndroidEdgeTestTags.DIAGNOSTICS_TAB
                    else -> AndroidEdgeTestTags.HOME_TAB
                }
                if (selectedView == view) {
                    Button(
                        modifier = Modifier.testTag(tag),
                        onClick = { selectedView = view }
                    ) {
                        Text(view)
                    }
                } else {
                    OutlinedButton(
                        modifier = Modifier.testTag(tag),
                        onClick = { selectedView = view }
                    ) {
                        Text(view)
                    }
                }
            }
        }
        if (selectedView == "Home") {
        StatusCard(
            connectionState = diagnostics.connectionState,
            serviceState = diagnostics.serviceState,
            notificationState = if (RuntimeNotificationPresenter.canPostNotifications(appContext)) {
                "granted"
            } else {
                "needs permission"
            },
            runtimeUrl = runtimeUrl,
            lastSuccessfulConnectionAt = diagnostics.lastSuccessfulConnectionAt,
            reconnectStatus = diagnostics.reconnectStatus
        )
        Row(
            horizontalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Button(
                modifier = Modifier.testTag(AndroidEdgeTestTags.START),
                onClick = {
                    startEdgeService(
                        appContext,
                        AndroidEdgeService.startIntent(
                            appContext,
                            runtimeMode,
                            runtimeUrl,
                            deviceId,
                            edgeToken
                        )
                    )
                }
            ) {
                Text("Start")
            }
            OutlinedButton(
                modifier = Modifier.testTag(AndroidEdgeTestTags.STOP),
                onClick = {
                    startEdgeService(appContext, AndroidEdgeService.stopIntent(appContext))
                }
            ) {
                Text("Stop")
            }
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            OutlinedButton(
                onClick = {
                    notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
                }
            ) {
                Text("Allow Notifications")
            }
        }
        HealthCard(
            notificationState = if (RuntimeNotificationPresenter.canPostNotifications(appContext)) {
                "granted"
            } else {
                "needs permission"
            },
            alertState = AndroidEdgeHealth.fullScreenAlertState(appContext),
            batteryState = AndroidEdgeHealth.batteryOptimizationState(appContext)
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(
                onClick = {
                    openSettings(appContext, AndroidEdgeHealth.appNotificationSettingsIntent(appContext))
                }
            ) {
                Text("Notification Settings")
            }
            OutlinedButton(
                onClick = {
                    openSettings(appContext, AndroidEdgeHealth.fullScreenAlertSettingsIntent(appContext))
                }
            ) {
                Text("Alert Settings")
            }
        }
        OutlinedButton(
            onClick = {
                openSettings(appContext, AndroidEdgeHealth.batterySettingsIntent(appContext))
            }
        ) {
            Text("Battery Settings")
        }
        OutlinedTextField(
            modifier = Modifier
                .fillMaxWidth()
                .testTag(AndroidEdgeTestTags.COMMAND_INPUT),
            value = textCommand,
            onValueChange = { textCommand = it },
            label = { Text("Ask OpenHalo from this phone") },
            minLines = 2
        )
        Button(
            modifier = Modifier.testTag(AndroidEdgeTestTags.COMMAND_SEND),
            enabled = textCommand.isNotBlank(),
            onClick = {
                startEdgeService(
                    appContext,
                    AndroidEdgeService.submitTextIntent(appContext, textCommand)
                )
                textCommand = ""
            }
        ) {
            Text("Send")
        }
        DiagnosticsCard("Latest Runtime Reply", diagnostics.inAppReply.ifBlank { "None yet" })
        DiagnosticsCard(
            "Recent Mobile History",
            diagnostics.recentEvents
                .ifBlank { AndroidEdgePreferences.formattedHistory(appContext) }
                .ifBlank { "None yet" }
        )
        DiagnosticsCard("Reconnect Health", reconnectSummary(diagnostics))
        } else if (selectedView == "Notifications") {
            Text(
                text = "Notification History",
                style = MaterialTheme.typography.titleMedium
            )
            if (notificationItems.isEmpty()) {
                DiagnosticsCard(
                    "Notifications",
                    "None yet",
                    modifier = Modifier.testTag(AndroidEdgeTestTags.NOTIFICATION_HISTORY)
                )
            } else {
                notificationItems.forEachIndexed { index, item ->
                    OutlinedButton(
                        modifier = Modifier
                            .fillMaxWidth()
                            .testTag(AndroidEdgeTestTags.NOTIFICATION_HISTORY),
                        onClick = { selectedNotificationIndex = index }
                    ) {
                        Text("${item.observedAt} ${item.title}")
                    }
                }
                val selected = notificationItems[
                    selectedNotificationIndex.coerceIn(0, notificationItems.lastIndex)
                ]
                DiagnosticsCard(
                    "Notification Detail",
                    "${selected.observedAt}\n${selected.title}\n${selected.body.ifBlank { "No detail" }}",
                    modifier = Modifier.testTag(AndroidEdgeTestTags.NOTIFICATION_DETAIL)
                )
            }
            DiagnosticsCard(
                "Recent Notification/Reply Log",
                AndroidEdgePreferences.formattedNotificationHistory(appContext).ifBlank { "None yet" }
            )
        } else {
        Column(modifier = Modifier.testTag(AndroidEdgeTestTags.DIAGNOSTICS_VIEW)) {
        HorizontalDivider()
        Text(
            text = "Connection Settings",
            style = MaterialTheme.typography.titleMedium
        )
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Text(
                text = "Persistent Runtime",
                style = MaterialTheme.typography.bodyLarge
            )
            Switch(
                checked = useStableRuntime,
                onCheckedChange = { checked ->
                    useStableRuntime = checked
                    val nextMode = if (checked) RUNTIME_MODE_STABLE else RUNTIME_MODE_DEVELOPMENT
                    runtimeUrl = runtimeUrlForMode(nextMode)
                    edgeToken = edgeTokenForMode(nextMode)
                }
            )
        }
        OutlinedTextField(
            modifier = Modifier.fillMaxWidth(),
            value = runtimeUrl,
            onValueChange = { runtimeUrl = it },
            label = { Text("Runtime WebSocket URL") },
            singleLine = true
        )
        OutlinedTextField(
            modifier = Modifier.fillMaxWidth(),
            value = deviceId,
            onValueChange = { deviceId = it },
            label = { Text("Device ID") },
            singleLine = true
        )
        OutlinedTextField(
            modifier = Modifier.fillMaxWidth(),
            value = edgeToken,
            onValueChange = { edgeToken = it },
            label = { Text("Edge Token") },
            singleLine = true,
            visualTransformation = PasswordVisualTransformation()
        )
        Row(
            horizontalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            OutlinedButton(
                onClick = {
                    startEdgeService(
                        appContext,
                        AndroidEdgeService.sendObservationsIntent(appContext)
                    )
                }
            ) {
                Text("Send Observations")
            }
        }
        OutlinedButton(
            onClick = {
                RuntimeNotificationPresenter.show(
                    appContext,
                    "OpenHalo local banner test"
                )
            }
        ) {
            Text("Test Notification")
        }
        OutlinedButton(
            onClick = {
                RuntimeNotificationPresenter.showUrgent(
                    appContext,
                    "OpenHalo urgent alert test"
                )
            }
        ) {
            Text("Test Urgent Alert")
        }
        DiagnosticsCard("Connection", diagnostics.connectionState)
        DiagnosticsCard("Service", diagnostics.serviceState)
        DiagnosticsCard("Runtime Mode", diagnostics.runtimeMode)
        DiagnosticsCard("Reconnect", reconnectSummary(diagnostics))
        DiagnosticsCard("Android Health", androidHealthSummary(appContext, diagnostics))
        DiagnosticsCard(
            "Edge Token",
            if (diagnostics.edgeToken.isBlank()) "Missing" else "Configured"
        )
        DiagnosticsCard("Registered Capabilities", diagnostics.registeredCapabilities)
        DiagnosticsCard("Recent Observations", diagnostics.recentObservations.ifBlank { "None yet" })
        DiagnosticsCard("Recent Actions", diagnostics.recentActions.ifBlank { "None yet" })
        DiagnosticsCard("Last Error", diagnostics.lastError.ifBlank { "None" })
        DiagnosticsCard("Last Sent Frame", diagnostics.lastSentFrame.ifBlank { "None yet" })
        DiagnosticsCard("Last Received Frame", diagnostics.lastReceivedFrame.ifBlank { "None yet" })
        }
        }
    }
}

private fun openSettings(context: Context, intent: Intent) {
    context.startActivity(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
}

private fun startEdgeService(context: Context, intent: android.content.Intent) {
    if (intent.action == AndroidEdgeService.ACTION_STOP) {
        context.startService(intent)
    } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
        context.startForegroundService(intent)
    } else {
        context.startService(intent)
    }
}

@Composable
private fun StatusCard(
    connectionState: String,
    serviceState: String,
    notificationState: String,
    runtimeUrl: String,
    lastSuccessfulConnectionAt: String,
    reconnectStatus: String
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.primaryContainer
        )
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Text(
                text = if (connectionState == "connected") "Ready" else "Not Connected",
                style = MaterialTheme.typography.titleLarge
            )
            Text(
                modifier = Modifier.testTag(AndroidEdgeTestTags.STATUS_SERVICE),
                text = "Service: $serviceState",
                style = MaterialTheme.typography.bodyMedium
            )
            Text(
                modifier = Modifier.testTag(AndroidEdgeTestTags.STATUS_CONNECTION),
                text = "Connection: $connectionState",
                style = MaterialTheme.typography.bodyMedium
            )
            Text(
                text = "Notifications: $notificationState",
                style = MaterialTheme.typography.bodyMedium
            )
            Text(
                text = runtimeUrl,
                style = MaterialTheme.typography.bodySmall
            )
            Text(
                text = "Last connected: ${lastSuccessfulConnectionAt.ifBlank { "never" }}",
                style = MaterialTheme.typography.bodySmall
            )
            Text(
                modifier = Modifier.testTag(AndroidEdgeTestTags.STATUS_RECONNECT),
                text = "Reconnect: $reconnectStatus",
                style = MaterialTheme.typography.bodySmall
            )
        }
    }
}

@Composable
private fun HealthCard(
    notificationState: String,
    alertState: String,
    batteryState: String
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.secondaryContainer
        )
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Text(
                text = "Android Health",
                style = MaterialTheme.typography.titleMedium
            )
            Text("Notifications: $notificationState")
            Text("Urgent alerts: $alertState")
            Text("Battery/background: $batteryState")
        }
    }
}

private fun reconnectSummary(diagnostics: EdgeDiagnostics): String =
    listOf(
        "status=${diagnostics.reconnectStatus}",
        "attempt=${diagnostics.reconnectAttempt}",
        "last_success=${diagnostics.lastSuccessfulConnectionAt.ifBlank { "never" }}",
        "last_disconnect=${diagnostics.lastDisconnectedAt.ifBlank { "never" }}",
        "reason=${diagnostics.lastDisconnectReason.ifBlank { "none" }}",
        "next=${diagnostics.nextReconnectAt.ifBlank { "none" }}"
    ).joinToString("\n")

private fun androidHealthSummary(context: Context, diagnostics: EdgeDiagnostics): String =
    listOf(
        "notification=${diagnostics.notificationHealth.ifBlank {
            if (RuntimeNotificationPresenter.canPostNotifications(context)) "granted" else "denied"
        }}",
        "full_screen_alert=${diagnostics.fullScreenAlertHealth.ifBlank {
            AndroidEdgeHealth.fullScreenAlertState(context)
        }}",
        "battery=${diagnostics.batteryHealth.ifBlank {
            AndroidEdgeHealth.batteryOptimizationState(context)
        }}"
    ).joinToString("\n")

@Composable
private fun DiagnosticsCard(title: String, body: String, modifier: Modifier = Modifier) {
    Card(
        modifier = modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant
        )
    ) {
        Column(
            modifier = Modifier.padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            Text(
                text = title,
                style = MaterialTheme.typography.titleSmall
            )
            Text(
                text = body,
                style = MaterialTheme.typography.bodySmall
            )
        }
    }
}

@Preview(showBackground = true)
@Composable
fun M17BootstrapScreenPreview() {
    OpenHaloAndroidEdgeTheme {
        M17BootstrapScreen()
    }
}
