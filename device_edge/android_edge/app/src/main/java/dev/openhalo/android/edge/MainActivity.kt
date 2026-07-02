package dev.openhalo.android.edge

import android.Manifest
import android.content.Context
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
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.compose.ui.text.input.PasswordVisualTransformation
import dev.openhalo.android.edge.ui.theme.OpenHaloAndroidEdgeTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            OpenHaloAndroidEdgeTheme {
                Scaffold(modifier = Modifier.fillMaxSize()) { innerPadding ->
                    M17BootstrapScreen(
                        modifier = Modifier.padding(innerPadding)
                    )
                }
            }
        }
    }
}

@Composable
fun M17BootstrapScreen(modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val appContext = context.applicationContext
    var diagnostics by remember { mutableStateOf(EdgeDiagnosticsStore.current()) }
    var useStableRuntime by remember {
        mutableStateOf(diagnostics.runtimeMode == RUNTIME_MODE_STABLE)
    }
    var runtimeUrl by remember { mutableStateOf(diagnostics.runtimeUrl) }
    var deviceId by remember { mutableStateOf(diagnostics.deviceId) }
    var edgeToken by remember { mutableStateOf(diagnostics.edgeToken) }
    val runtimeMode = if (useStableRuntime) RUNTIME_MODE_STABLE else RUNTIME_MODE_DEVELOPMENT
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
            text = "M17 native Device Edge diagnostic session",
            style = MaterialTheme.typography.bodyLarge
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
            Button(
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
                Text("Connect")
            }
            OutlinedButton(
                onClick = {
                    startEdgeService(appContext, AndroidEdgeService.stopIntent(appContext))
                }
            ) {
                Text("Disconnect")
            }
        }
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
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                OutlinedButton(
                    onClick = {
                        notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
                    }
                ) {
                    Text("Allow Notifications")
                }
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
        DiagnosticsCard(
            "Edge Token",
            if (diagnostics.edgeToken.isBlank()) "Missing" else "Configured"
        )
        DiagnosticsCard("Registered Capabilities", diagnostics.registeredCapabilities)
        DiagnosticsCard("Recent Observations", diagnostics.recentObservations.ifBlank { "None yet" })
        DiagnosticsCard("Recent Actions", diagnostics.recentActions.ifBlank { "None yet" })
        DiagnosticsCard("In-App Reply", diagnostics.inAppReply.ifBlank { "None yet" })
        DiagnosticsCard("Last Error", diagnostics.lastError.ifBlank { "None" })
        DiagnosticsCard("Last Sent Frame", diagnostics.lastSentFrame.ifBlank { "None yet" })
        DiagnosticsCard("Last Received Frame", diagnostics.lastReceivedFrame.ifBlank { "None yet" })
    }
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
private fun DiagnosticsCard(title: String, body: String) {
    Card(
        modifier = Modifier.fillMaxWidth(),
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
