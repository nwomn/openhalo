package dev.openhalo.android.edge

import android.Manifest
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.ime
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import dev.openhalo.android.edge.ui.theme.OpenHaloAndroidEdgeTheme
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

private val Ink = Color(0xFF050505)
private val Muted = Color(0xFF9A9A9A)
private val Hairline = Color(0xFFE8E8E8)
private val Panel = Color(0xFFFFFFFF)
private val SoftPanel = Color(0xFFF5F5F5)
private val Success = Color(0xFF2DB36A)
private val Danger = Color(0xFFFF5A52)
private val HiddenText = Color(0x01000000)
private val ChatTimeFormatter: DateTimeFormatter =
    DateTimeFormatter.ofPattern("HH:mm").withZone(ZoneId.systemDefault())

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val initialView = intent.getStringExtra(EXTRA_INITIAL_VIEW) ?: VIEW_CONNECT
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
        const val VIEW_CONNECT = "Connect"
        const val VIEW_GLOBAL_CHAT = "Global Chat"
        const val VIEW_SETTINGS = "Settings"
        const val VIEW_NOTIFICATIONS = VIEW_GLOBAL_CHAT
    }
}

object AndroidEdgeTestTags {
    const val CONNECT_TAB = "openhalo.connect.tab"
    const val GLOBAL_CHAT_TAB = "openhalo.global_chat.tab"
    const val SETTINGS_TAB = "openhalo.settings.tab"
    const val CONNECT_PRIMARY_ACTION = "openhalo.connect.primary_action"
    const val GLOBAL_CHAT_LIST = "openhalo.global_chat.list"
    const val GLOBAL_CHAT_INPUT = "openhalo.global_chat.input"
    const val GLOBAL_CHAT_SEND = "openhalo.global_chat.send"
    const val SETTINGS_RUNTIME_URL = "openhalo.settings.runtime_url"
    const val SETTINGS_DEVICE_NAME = "openhalo.settings.device_name"
    const val SETTINGS_RUNTIME_URL_EDITOR = "openhalo.settings.runtime_url.editor"
    const val SETTINGS_DEVICE_NAME_EDITOR = "openhalo.settings.device_name.editor"
    const val SETTINGS_EDIT_SAVE = "openhalo.settings.edit.save"
    const val SETTINGS_PROTOCOL_ROW = "openhalo.settings.protocol.row"
    const val SETTINGS_NOTIFICATION_ROW = "openhalo.settings.notification.row"
    const val SETTINGS_KEEPALIVE_ROW = "openhalo.settings.keepalive.row"
    const val SETTINGS_SCREEN_CONTEXT_ROW = "openhalo.settings.screen_context.row"
    const val SETTINGS_ACCESSIBILITY_ROW = "openhalo.settings.accessibility.row"
    const val ACCESSIBILITY_DISABLED_NOTICE = "openhalo.accessibility.disabled_notice"
    const val SETTINGS_BATTERY_ROW = "openhalo.settings.battery.row"
    const val SETTINGS_LOCAL_NETWORK_ROW = "openhalo.settings.local_network.row"
    const val SETTINGS_BUILD_ROW = "openhalo.settings.build_row"
    const val DEVELOPER_DIAGNOSTICS_VIEW = "openhalo.developer_diagnostics.view"
    const val DEVELOPER_DIAGNOSTICS_ROW = "openhalo.developer_diagnostics.row"
    const val STATUS_CONNECTION = "openhalo.status.connection"
    const val STATUS_SERVICE = "openhalo.status.service"
    const val STATUS_RECONNECT = "openhalo.status.reconnect"
    const val NOTIFICATION_HISTORY = "openhalo.notification.history"
    const val NOTIFICATION_DETAIL = "openhalo.notification.detail"
}

@Composable
fun M17BootstrapScreen(
    initialView: String = MainActivity.VIEW_CONNECT,
    modifier: Modifier = Modifier
) {
    val context = LocalContext.current
    val appContext = context.applicationContext
    val storedConfig = remember { AndroidEdgePreferences.loadConfig(appContext) }
    var diagnostics by remember { mutableStateOf(EdgeDiagnosticsStore.current()) }
    var useStableRuntime by remember { mutableStateOf(storedConfig.runtimeMode == RUNTIME_MODE_STABLE) }
    var runtimeUrl by remember { mutableStateOf(storedConfig.runtimeUrl) }
    var deviceId by remember { mutableStateOf(storedConfig.deviceId) }
    var edgeToken by remember { mutableStateOf(storedConfig.edgeToken) }
    var backgroundKeepAlive by remember {
        mutableStateOf(AndroidEdgePreferences.backgroundKeepAliveEnabled(appContext))
    }
    var screenContextObservation by remember {
        mutableStateOf(AndroidEdgePreferences.screenContextObservationEnabled(appContext))
    }
    var accessibilityServiceState by remember {
        mutableStateOf(AndroidEdgeHealth.accessibilityServiceState(appContext))
    }
    var showAccessibilityDisabledNotice by remember { mutableStateOf(false) }
    var selectedView by remember { mutableStateOf(normalizeInitialView(initialView)) }
    var diagnosticsUnlocked by remember { mutableStateOf(false) }
    var diagnosticsOpen by remember { mutableStateOf(initialView == "Diagnostics") }
    var buildTapCount by remember { mutableIntStateOf(0) }
    var textCommand by remember { mutableStateOf("") }
    var historyVersion by remember { mutableIntStateOf(0) }
    val runtimeMode = if (useStableRuntime) RUNTIME_MODE_STABLE else RUNTIME_MODE_DEVELOPMENT
    val notificationPermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) {
        startEdgeService(appContext, AndroidEdgeService.sendObservationsIntent(appContext))
    }

    fun refreshAccessibilityState() {
        val nextState = AndroidEdgeHealth.accessibilityServiceState(appContext)
        accessibilityServiceState = nextState
        if (nextState == "enabled") {
            AndroidEdgePreferences.markAccessibilityServiceObservedEnabled(appContext)
            showAccessibilityDisabledNotice = false
        } else {
            showAccessibilityDisabledNotice = shouldShowAccessibilityDisabledNotice(
                screenContextObservation = screenContextObservation,
                accessibilityServiceState = nextState,
                accessibilityWasObservedEnabled =
                    AndroidEdgePreferences.accessibilityServiceWasObservedEnabled(appContext),
                noticeDismissed =
                    AndroidEdgePreferences.accessibilityDisabledNoticeDismissed(appContext)
            )
        }
    }

    DisposableEffect(Unit) {
        val unsubscribe = EdgeDiagnosticsStore.subscribe { next ->
            (context as? ComponentActivity)?.runOnUiThread {
                diagnostics = next
                historyVersion += 1
            } ?: run {
                diagnostics = next
                historyVersion += 1
            }
        }
        onDispose { unsubscribe() }
    }

    DisposableEffect(context) {
        val activity = context as? ComponentActivity
        if (activity == null) {
            onDispose { }
        } else {
            val observer = LifecycleEventObserver { _, event ->
                if (event == Lifecycle.Event.ON_RESUME) {
                    refreshAccessibilityState()
                }
            }
            activity.lifecycle.addObserver(observer)
            refreshAccessibilityState()
            onDispose { activity.lifecycle.removeObserver(observer) }
        }
    }

    val currentNotificationState = notificationState(appContext)
    val connectionState = productConnectionState(diagnostics, runtimeUrl, currentNotificationState)

    Box(
        modifier = modifier
            .fillMaxSize()
            .background(Color.White)
    ) {
        when {
            diagnosticsOpen -> DeveloperDiagnosticsScreen(
                diagnostics = diagnostics,
                useStableRuntime = useStableRuntime,
                runtimeUrl = runtimeUrl,
                deviceId = deviceId,
                edgeToken = edgeToken,
                onStableRuntimeChanged = { checked ->
                    useStableRuntime = checked
                    val nextMode = if (checked) RUNTIME_MODE_STABLE else RUNTIME_MODE_DEVELOPMENT
                    runtimeUrl = runtimeUrlForMode(nextMode)
                    edgeToken = edgeTokenForMode(nextMode)
                    saveConfig(appContext, nextMode, runtimeUrl, deviceId, edgeToken)
                },
                onRuntimeUrlChanged = {
                    runtimeUrl = it
                    saveConfig(appContext, runtimeMode, runtimeUrl, deviceId, edgeToken)
                },
                onDeviceIdChanged = {
                    deviceId = it
                    saveConfig(appContext, runtimeMode, runtimeUrl, deviceId, edgeToken)
                },
                onEdgeTokenChanged = {
                    edgeToken = it
                    saveConfig(appContext, runtimeMode, runtimeUrl, deviceId, edgeToken)
                },
                onSendObservations = {
                    startEdgeService(appContext, AndroidEdgeService.sendObservationsIntent(appContext))
                },
                onTestNotification = {
                    RuntimeNotificationPresenter.show(appContext, "OpenHalo local banner test")
                },
                onTestUrgentAlert = {
                    RuntimeNotificationPresenter.showUrgent(appContext, "OpenHalo urgent alert test")
                }
            )

            selectedView == MainActivity.VIEW_CONNECT -> ConnectScreen(
                diagnostics = diagnostics,
                runtimeUrl = runtimeUrl,
                deviceId = deviceId,
                connectionState = connectionState,
                onSettings = {
                    selectedView = MainActivity.VIEW_SETTINGS
                    diagnosticsOpen = false
                },
                onPrimaryAction = {
                    when (connectionState) {
                        "needs_setup" -> selectedView = MainActivity.VIEW_SETTINGS
                        "connected", "connecting", "reconnecting" -> {
                            startEdgeService(appContext, AndroidEdgeService.stopIntent(appContext))
                        }
                        "restricted" -> openSettings(
                            appContext,
                            AndroidEdgeHealth.appNotificationSettingsIntent(appContext)
                        )
                        else -> {
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
                    }
                }
            )

            selectedView == MainActivity.VIEW_GLOBAL_CHAT -> GlobalChatScreen(
                diagnostics = diagnostics,
                textCommand = textCommand,
                historyVersion = historyVersion,
                onTextCommandChanged = { textCommand = it },
                onSend = {
                    startEdgeService(appContext, AndroidEdgeService.submitTextIntent(appContext, textCommand))
                    textCommand = ""
                    historyVersion += 1
                }
            )

            else -> SettingsScreen(
                diagnostics = diagnostics,
                runtimeMode = runtimeMode,
                runtimeUrl = runtimeUrl,
                deviceId = deviceId,
                notificationState = currentNotificationState,
                backgroundKeepAlive = backgroundKeepAlive,
                screenContextObservation = screenContextObservation,
                accessibilityServiceState = accessibilityServiceState,
                diagnosticsUnlocked = diagnosticsUnlocked,
                onRuntimeUrlChanged = {
                    runtimeUrl = it
                    saveConfig(appContext, runtimeMode, runtimeUrl, deviceId, edgeToken)
                },
                onDeviceIdChanged = {
                    deviceId = it
                    saveConfig(appContext, runtimeMode, runtimeUrl, deviceId, edgeToken)
                },
                onOpenNotificationSettings = {
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                        notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
                    } else {
                        openSettings(appContext, AndroidEdgeHealth.appNotificationSettingsIntent(appContext))
                    }
                },
                onOpenAlertSettings = {
                    openSettings(appContext, AndroidEdgeHealth.fullScreenAlertSettingsIntent(appContext))
                },
                onOpenBatterySettings = {
                    openSettings(appContext, AndroidEdgeHealth.batterySettingsIntent(appContext))
                },
                onOpenAccessibilitySettings = {
                    accessibilityServiceState = AndroidEdgeHealth.accessibilityServiceState(appContext)
                    openSettings(appContext, AndroidEdgeHealth.accessibilitySettingsIntent())
                },
                onBackgroundKeepAliveChanged = { enabled ->
                    backgroundKeepAlive = enabled
                    AndroidEdgePreferences.saveBackgroundKeepAliveEnabled(appContext, enabled)
                },
                onScreenContextObservationChanged = { enabled ->
                    screenContextObservation = enabled
                    AndroidEdgePreferences.saveScreenContextObservationEnabled(appContext, enabled)
                    if (enabled && accessibilityServiceState != "enabled") {
                        showAccessibilityDisabledNotice = shouldShowAccessibilityDisabledNotice(
                            screenContextObservation = true,
                            accessibilityServiceState = accessibilityServiceState,
                            accessibilityWasObservedEnabled =
                                AndroidEdgePreferences.accessibilityServiceWasObservedEnabled(appContext),
                            noticeDismissed =
                                AndroidEdgePreferences.accessibilityDisabledNoticeDismissed(appContext)
                        )
                    }
                    startEdgeService(appContext, AndroidEdgeService.sendObservationsIntent(appContext))
                },
                onResetConnection = {
                    startEdgeService(appContext, AndroidEdgeService.stopIntent(appContext))
                    runtimeUrl = runtimeUrlForMode(runtimeMode)
                    edgeToken = edgeTokenForMode(runtimeMode)
                    saveConfig(appContext, runtimeMode, runtimeUrl, deviceId, edgeToken)
                },
                onClearCache = {
                    AndroidEdgePreferences.clearHistory(appContext)
                    historyVersion += 1
                },
                onBuildTap = {
                    buildTapCount += 1
                    if (buildTapCount >= 7) {
                        diagnosticsUnlocked = true
                    }
                },
                onOpenDiagnostics = { diagnosticsOpen = true }
            )
        }

        if (!diagnosticsOpen) {
            BottomNav(
                selectedView = selectedView,
                modifier = Modifier.align(Alignment.BottomCenter),
                onSelect = {
                    selectedView = it
                    diagnosticsOpen = false
                }
            )
        }
        if (showAccessibilityDisabledNotice) {
            AccessibilityDisabledNoticeDialog(
                onOpenSettings = {
                    AndroidEdgePreferences.dismissAccessibilityDisabledNotice(appContext)
                    showAccessibilityDisabledNotice = false
                    openSettings(appContext, AndroidEdgeHealth.accessibilitySettingsIntent())
                },
                onDismiss = {
                    AndroidEdgePreferences.dismissAccessibilityDisabledNotice(appContext)
                    showAccessibilityDisabledNotice = false
                }
            )
        }
    }
}

@Composable
private fun AccessibilityDisabledNoticeDialog(
    onOpenSettings: () -> Unit,
    onDismiss: () -> Unit
) {
    AlertDialog(
        modifier = Modifier.testTag(AndroidEdgeTestTags.ACCESSIBILITY_DISABLED_NOTICE),
        onDismissRequest = onDismiss,
        title = { Text("无障碍观察已关闭") },
        text = {
            Text(
                "系统已关闭 OpenHalo 的无障碍观察。MIUI 手动划掉或清理应用可能会强停 Edge 并取消该授权；需要重新在系统无障碍设置中开启。"
            )
        },
        confirmButton = {
            Button(onClick = onOpenSettings) {
                Text("去开启")
            }
        },
        dismissButton = {
            OutlinedButton(onClick = onDismiss) {
                Text("稍后")
            }
        }
    )
}

private fun normalizeInitialView(initialView: String): String =
    when (initialView) {
        MainActivity.VIEW_GLOBAL_CHAT, "Notifications" -> MainActivity.VIEW_GLOBAL_CHAT
        MainActivity.VIEW_SETTINGS, "Diagnostics" -> MainActivity.VIEW_SETTINGS
        else -> MainActivity.VIEW_CONNECT
    }

internal fun shouldShowAccessibilityDisabledNotice(
    screenContextObservation: Boolean,
    accessibilityServiceState: String,
    accessibilityWasObservedEnabled: Boolean,
    noticeDismissed: Boolean
): Boolean =
    screenContextObservation &&
        accessibilityServiceState != "enabled" &&
        accessibilityWasObservedEnabled &&
        !noticeDismissed

@Composable
private fun ConnectScreen(
    diagnostics: EdgeDiagnostics,
    runtimeUrl: String,
    deviceId: String,
    connectionState: String,
    onSettings: () -> Unit,
    onPrimaryAction: () -> Unit
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(start = 24.dp, end = 24.dp, top = 46.dp, bottom = 120.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text("OpenHalo", color = Ink, fontSize = 36.sp, fontWeight = FontWeight.Light)
            IconButton(onClick = onSettings) {
                Text("⚙", color = Muted, fontSize = 32.sp)
            }
        }
        Spacer(Modifier.height(34.dp))
        HorizontalDivider(color = Hairline)
        Spacer(Modifier.weight(1f))
        Text(connectionTitleZh(connectionState), color = Muted, fontSize = 18.sp)
        Spacer(Modifier.height(44.dp))
        Text(endpointSummary(runtimeUrl), color = Ink, fontSize = 22.sp)
        Spacer(Modifier.height(8.dp))
        Text(connectionSubtitle(diagnostics), color = Muted, fontSize = 18.sp)
        Spacer(Modifier.height(56.dp))
        ConnectionStateSelector(connectionState)
        Spacer(Modifier.height(60.dp))
        Button(
            modifier = Modifier
                .size(210.dp)
                .testTag(AndroidEdgeTestTags.CONNECT_PRIMARY_ACTION),
            shape = CircleShape,
            colors = ButtonDefaults.buttonColors(containerColor = Ink, contentColor = Color.White),
            onClick = onPrimaryAction,
            enabled = connectionState != "connecting"
        ) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text("((•))", color = Color.White, fontSize = 38.sp, fontWeight = FontWeight.Bold)
                    Spacer(Modifier.height(18.dp))
                    Text(
                        primaryActionLabel(connectionState).uppercase(),
                        color = Color.White,
                        fontSize = 15.sp,
                        letterSpacing = 3.sp
                    )
                }
                Box(
                    modifier = Modifier
                        .align(Alignment.BottomEnd)
                        .padding(end = 20.dp, bottom = 34.dp)
                        .size(18.dp)
                        .clip(CircleShape)
                        .background(statusDotColor(connectionState))
                        .border(2.dp, Color.White, CircleShape)
                )
            }
        }
        Spacer(Modifier.weight(1.4f))
        Text(
            text = deviceId.ifBlank { "android edge" },
            color = Color.Transparent,
            modifier = Modifier.testTag(AndroidEdgeTestTags.STATUS_SERVICE)
        )
        Text(
            text = "Connection: ${diagnostics.connectionState}",
            color = Color.Transparent,
            modifier = Modifier.testTag(AndroidEdgeTestTags.STATUS_CONNECTION)
        )
        Text(
            text = "Reconnect: ${diagnostics.reconnectStatus}",
            color = Color.Transparent,
            modifier = Modifier.testTag(AndroidEdgeTestTags.STATUS_RECONNECT)
        )
    }
}

@Composable
private fun ConnectionStateSelector(connectionState: String) {
    Row(horizontalArrangement = Arrangement.spacedBy(9.dp)) {
        listOf(
            "disconnected" to "断开",
            "connecting" to "连接中",
            "connected" to "已连接",
            "error" to "错误"
        ).forEach { (state, label) ->
            val selected = state == normalizedSelectorState(connectionState)
            Box(
                modifier = Modifier
                    .clip(RoundedCornerShape(4.dp))
                    .background(if (selected) Ink else SoftPanel)
                    .border(1.dp, if (selected) Ink else Hairline, RoundedCornerShape(4.dp))
                    .padding(horizontal = 15.dp, vertical = 9.dp)
            ) {
                Text(
                    label,
                    color = when {
                        selected -> Color.White
                        state == "error" -> Danger
                        else -> Muted
                    },
                    fontSize = 16.sp
                )
            }
        }
    }
}

@Composable
private fun GlobalChatScreen(
    diagnostics: EdgeDiagnostics,
    textCommand: String,
    historyVersion: Int,
    onTextCommandChanged: (String) -> Unit,
    onSend: () -> Unit
) {
    val context = LocalContext.current
    val density = LocalDensity.current
    val imeBottom = with(density) { WindowInsets.ime.getBottom(this).toDp() }
    val bottomReserve = if (imeBottom > 0.dp) imeBottom else 108.dp
    val history = remember(historyVersion, diagnostics.recentEvents, diagnostics.inAppReply) {
        AndroidEdgePreferences.historyItems(context.applicationContext)
            .filter(::isConversationHistoryItem)
    }
    val chatScrollState = rememberScrollState()
    val renderedMessageCount = history.size + if (diagnostics.inAppReply.isNotBlank()) 1 else 0
    LaunchedEffect(renderedMessageCount, historyVersion, diagnostics.inAppReply, chatScrollState.maxValue) {
        if (renderedMessageCount > 0 && chatScrollState.maxValue > 0) {
            chatScrollState.animateScrollTo(chatScrollState.maxValue)
        }
    }
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(top = 46.dp)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 24.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.Bottom
        ) {
            Column {
                Text("全局对话", color = Ink, fontSize = 34.sp, fontWeight = FontWeight.Light)
                Text("跨设备 · ${history.size.coerceAtLeast(3)} 条设备记录", color = Muted, fontSize = 18.sp)
            }
            Text(">_", color = Muted, fontSize = 28.sp)
        }
        Spacer(Modifier.height(28.dp))
        HorizontalDivider(color = Hairline)
        Column(
            modifier = Modifier
                .weight(1f)
                .verticalScroll(chatScrollState)
                .padding(horizontal = 24.dp, vertical = 24.dp)
                .testTag(AndroidEdgeTestTags.GLOBAL_CHAT_LIST),
            verticalArrangement = Arrangement.spacedBy(18.dp)
        ) {
            Text("今天", color = Color(0xFFC8C8C8), fontSize = 18.sp, modifier = Modifier.align(Alignment.CenterHorizontally))
            if (history.isEmpty() && diagnostics.inAppReply.isBlank()) {
                ChatMeta("Personal Runtime · 当前无记录")
                RuntimeBubble("连接后，来自终端、手机和桌面的对话会在这里汇总。")
            } else {
                history.asReversed().forEach { item ->
                    ChatHistoryItem(item)
                }
                if (diagnostics.inAppReply.isNotBlank()) {
                    ChatMeta("Personal Runtime · delivered")
                    RuntimeBubble(diagnostics.inAppReply)
                }
            }
        }
        ChatComposer(
            value = textCommand,
            enabled = textCommand.isNotBlank(),
            onValueChange = onTextCommandChanged,
            onSend = onSend
        )
        Spacer(Modifier.height(bottomReserve))
    }
}

@Composable
private fun ChatHistoryItem(item: AndroidEdgeHistoryItem) {
    when {
        item.title.contains("mobile.input") -> {
            ChatMeta("▯ iPhone · ${chatTimestamp(item.observedAt)}", alignEnd = true)
            UserBubble(item.body.ifBlank { item.title })
        }
        item.kind == "notification" || item.kind == "reply" -> {
            ChatMeta("Personal Runtime · ${chatTimestamp(item.observedAt)}")
            RuntimeBubble(
                listOf(item.title, item.body)
                    .filter { it.isNotBlank() }
                    .joinToString("\n")
            )
        }
    }
}

private fun isConversationHistoryItem(item: AndroidEdgeHistoryItem): Boolean =
    item.title.contains("mobile.input") ||
        item.kind == "notification" ||
        item.kind == "reply"

private fun chatTimestamp(observedAt: String): String =
    runCatching { ChatTimeFormatter.format(Instant.parse(observedAt)) }
        .getOrDefault("--:--")

@Composable
private fun ChatMeta(text: String, alignEnd: Boolean = false) {
    Text(
        text,
        color = Muted,
        fontSize = 16.sp,
        modifier = Modifier.fillMaxWidth(),
        textAlign = if (alignEnd) TextAlign.End else TextAlign.Start
    )
}

@Composable
private fun UserBubble(text: String) {
    Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.CenterEnd) {
        Text(
            text,
            color = Color.White,
            fontSize = 20.sp,
            lineHeight = 30.sp,
            modifier = Modifier
                .fillMaxWidth(0.78f)
                .clip(RoundedCornerShape(3.dp))
                .background(Ink)
                .padding(horizontal = 18.dp, vertical = 16.dp)
        )
    }
}

@Composable
private fun RuntimeBubble(text: String) {
    Text(
        text,
        color = Ink,
        fontSize = 20.sp,
        lineHeight = 31.sp,
        modifier = Modifier
            .fillMaxWidth(0.88f)
            .border(1.dp, Color(0xFFDCDCDC), RoundedCornerShape(3.dp))
            .padding(horizontal = 18.dp, vertical = 16.dp)
    )
}

@Composable
private fun SystemBubble(text: String) {
    Text(
        text,
        color = Ink,
        fontSize = 18.sp,
        modifier = Modifier
            .fillMaxWidth(0.78f)
            .clip(RoundedCornerShape(3.dp))
            .background(SoftPanel)
            .padding(horizontal = 16.dp, vertical = 12.dp)
    )
}

@Composable
private fun ChatComposer(
    value: String,
    enabled: Boolean,
    onValueChange: (String) -> Unit,
    onSend: () -> Unit,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .background(Color.White)
            .border(1.dp, Hairline)
            .padding(horizontal = 16.dp, vertical = 12.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(
            modifier = Modifier
                .weight(1f)
                .height(54.dp)
                .clip(RoundedCornerShape(3.dp))
                .background(SoftPanel)
                .border(1.dp, Color(0xFFDADADA), RoundedCornerShape(3.dp))
                .padding(horizontal = 14.dp),
            contentAlignment = Alignment.CenterStart
        ) {
            if (value.isBlank()) {
                Text("向 Runtime 发送消息...", color = Color(0xFFC2C2C2), fontSize = 18.sp)
            }
            BasicTextField(
                modifier = Modifier
                    .fillMaxWidth()
                    .testTag(AndroidEdgeTestTags.GLOBAL_CHAT_INPUT),
                value = value,
                onValueChange = onValueChange,
                singleLine = true,
                textStyle = TextStyle(color = Ink, fontSize = 18.sp)
            )
        }
        Button(
            modifier = Modifier
                .size(width = 46.dp, height = 54.dp)
                .testTag(AndroidEdgeTestTags.GLOBAL_CHAT_SEND),
            shape = RoundedCornerShape(4.dp),
            enabled = enabled,
            colors = ButtonDefaults.buttonColors(containerColor = Ink, contentColor = Color.White),
            contentPadding = androidx.compose.foundation.layout.PaddingValues(0.dp),
            onClick = onSend
        ) {
            SendArrowIcon(color = if (enabled) Color.White else Color(0xFFB8B8B8))
        }
    }
}

@Composable
private fun SendArrowIcon(color: Color) {
    Canvas(modifier = Modifier.size(26.dp)) {
        val strokeWidth = 3.2.dp.toPx()
        val shaftX = size.width * 0.5f
        val topY = size.height * 0.18f
        val bottomY = size.height * 0.82f
        drawLine(
            color = color,
            start = androidx.compose.ui.geometry.Offset(shaftX, bottomY),
            end = androidx.compose.ui.geometry.Offset(shaftX, topY),
            strokeWidth = strokeWidth,
            cap = StrokeCap.Round
        )
        val head = Path().apply {
            moveTo(size.width * 0.22f, size.height * 0.42f)
            lineTo(shaftX, topY)
            lineTo(size.width * 0.78f, size.height * 0.42f)
        }
        drawPath(
            path = head,
            color = color,
            style = Stroke(
                width = strokeWidth,
                cap = StrokeCap.Round,
                join = StrokeJoin.Round
            )
        )
    }
}

@Composable
private fun SettingsScreen(
    diagnostics: EdgeDiagnostics,
    runtimeMode: String,
    runtimeUrl: String,
    deviceId: String,
    notificationState: String,
    backgroundKeepAlive: Boolean,
    screenContextObservation: Boolean,
    accessibilityServiceState: String,
    diagnosticsUnlocked: Boolean,
    onRuntimeUrlChanged: (String) -> Unit,
    onDeviceIdChanged: (String) -> Unit,
    onOpenNotificationSettings: () -> Unit,
    onOpenAlertSettings: () -> Unit,
    onOpenBatterySettings: () -> Unit,
    onOpenAccessibilitySettings: () -> Unit,
    onBackgroundKeepAliveChanged: (Boolean) -> Unit,
    onScreenContextObservationChanged: (Boolean) -> Unit,
    onResetConnection: () -> Unit,
    onClearCache: () -> Unit,
    onBuildTap: () -> Unit,
    onOpenDiagnostics: () -> Unit
) {
    var editTarget by remember { mutableStateOf<SettingsEditTarget?>(null) }
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(start = 24.dp, end = 24.dp, top = 56.dp, bottom = 190.dp),
        verticalArrangement = Arrangement.spacedBy(22.dp)
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text("设置", color = Ink, fontSize = 34.sp, fontWeight = FontWeight.Light)
            Text(
                "v${BuildConfig.VERSION_NAME}",
                color = Muted,
                fontSize = 18.sp,
                modifier = Modifier
                    .testTag(AndroidEdgeTestTags.SETTINGS_BUILD_ROW)
                    .clickable(onClick = onBuildTap)
            )
        }
        if (diagnosticsUnlocked) {
            OutlinedButton(
                modifier = Modifier
                    .fillMaxWidth()
                    .testTag(AndroidEdgeTestTags.DEVELOPER_DIAGNOSTICS_ROW),
                onClick = onOpenDiagnostics
            ) {
                Text("Developer Diagnostics")
            }
        }
        SettingsSection("运行时连接") {
            EditableSettingsRow(
                title = "服务器地址",
                value = endpointSummary(runtimeUrl),
                tag = AndroidEdgeTestTags.SETTINGS_RUNTIME_URL,
                onClick = { editTarget = SettingsEditTarget.RuntimeUrl(runtimeUrl) }
            )
            SettingsDivider()
            EditableSettingsRow(
                title = "设备名称",
                value = deviceId.ifBlank { "我的 iPhone" },
                tag = AndroidEdgeTestTags.SETTINGS_DEVICE_NAME,
                onClick = { editTarget = SettingsEditTarget.DeviceName(deviceId) }
            )
            SettingsDivider()
            StaticSettingsRow(
                title = "连接协议",
                value = "WebSocket",
                tag = AndroidEdgeTestTags.SETTINGS_PROTOCOL_ROW
            )
        }
        SettingsSection("通知与权限") {
            ToggleSettingsRow(
                title = "推送通知",
                checked = notificationState == "granted",
                tag = AndroidEdgeTestTags.SETTINGS_NOTIFICATION_ROW,
                onCheckedChange = { onOpenNotificationSettings() }
            )
            SettingsDivider()
            ToggleSettingsRow(
                title = "后台保活",
                checked = backgroundKeepAlive,
                tag = AndroidEdgeTestTags.SETTINGS_KEEPALIVE_ROW,
                onCheckedChange = onBackgroundKeepAliveChanged
            )
            SettingsDivider()
            ToggleSettingsRow(
                title = "屏幕上下文",
                checked = screenContextObservation,
                tag = AndroidEdgeTestTags.SETTINGS_SCREEN_CONTEXT_ROW,
                onCheckedChange = onScreenContextObservationChanged
            )
            SettingsDivider()
            PermissionRow(
                title = "无障碍观察",
                value = accessibilityServiceState,
                tag = AndroidEdgeTestTags.SETTINGS_ACCESSIBILITY_ROW,
                onClick = onOpenAccessibilitySettings
            )
            SettingsDivider()
            PermissionRow(
                title = "电池策略",
                value = AndroidEdgeHealth.backgroundPermissionGuidance(
                    batteryState = diagnostics.batteryHealth.ifBlank {
                        AndroidEdgeHealth.batteryOptimizationState(LocalContext.current)
                    }
                ),
                tag = AndroidEdgeTestTags.SETTINGS_BATTERY_ROW,
                onClick = onOpenBatterySettings
            )
            SettingsDivider()
            StaticSettingsRow(
                title = "本地网络权限",
                value = "Android 自动授权",
                tag = AndroidEdgeTestTags.SETTINGS_LOCAL_NETWORK_ROW,
                showChevron = false
            )
        }
        SettingsSection("操作") {
            ActionSettingsRow("重置连接", "↻", onResetConnection)
            SettingsDivider()
            ActionSettingsRow("清除本地缓存", "▢", onClearCache)
        }
        Text("关于", color = Muted, fontSize = 18.sp, fontWeight = FontWeight.Bold)
        SettingsRowShell {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(58.dp)
                    .clickable(onClick = onBuildTap),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    "Build",
                    color = Ink,
                    fontSize = 22.sp
                )
                Text("OpenHalo Android Edge ${BuildConfig.VERSION_NAME}", color = Muted, fontSize = 16.sp)
            }
        }
        Text(
            "Runtime mode: $runtimeMode",
            color = Color.Transparent,
            modifier = Modifier.height(1.dp)
        )
    }
    editTarget?.let { target ->
        SettingsEditDialog(
            target = target,
            onDismiss = { editTarget = null },
            onSave = { value ->
                when (target) {
                    is SettingsEditTarget.RuntimeUrl -> onRuntimeUrlChanged(value)
                    is SettingsEditTarget.DeviceName -> onDeviceIdChanged(value)
                }
                editTarget = null
            }
        )
    }
}

@Composable
private fun SettingsSection(title: String, content: @Composable ColumnScope.() -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(title, color = Muted, fontSize = 18.sp, fontWeight = FontWeight.Bold)
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(6.dp),
            colors = CardDefaults.cardColors(containerColor = Panel),
            border = androidx.compose.foundation.BorderStroke(1.dp, Hairline)
        ) {
            Column(
                modifier = Modifier.padding(horizontal = 22.dp, vertical = 10.dp),
                content = content
            )
        }
    }
}

@Composable
private fun SettingsRowShell(modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    Card(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(6.dp),
        colors = CardDefaults.cardColors(containerColor = Panel),
        border = androidx.compose.foundation.BorderStroke(1.dp, Hairline)
    ) {
        Column(modifier = Modifier.padding(horizontal = 22.dp, vertical = 14.dp)) {
            content()
        }
    }
}

private sealed class SettingsEditTarget(
    val title: String,
    val value: String,
    val tag: String
) {
    class RuntimeUrl(value: String) : SettingsEditTarget(
        "服务器地址",
        value,
        AndroidEdgeTestTags.SETTINGS_RUNTIME_URL_EDITOR
    )

    class DeviceName(value: String) : SettingsEditTarget(
        "设备名称",
        value,
        AndroidEdgeTestTags.SETTINGS_DEVICE_NAME_EDITOR
    )
}

@Composable
private fun SettingsEditDialog(
    target: SettingsEditTarget,
    onDismiss: () -> Unit,
    onSave: (String) -> Unit
) {
    var draft by remember(target) { mutableStateOf(target.value) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(target.title) },
        text = {
            OutlinedTextField(
                modifier = Modifier
                    .fillMaxWidth()
                    .testTag(target.tag),
                value = draft,
                onValueChange = { draft = it },
                singleLine = true
            )
        },
        confirmButton = {
            Button(
                modifier = Modifier.testTag(AndroidEdgeTestTags.SETTINGS_EDIT_SAVE),
                onClick = { onSave(draft.trim()) }
            ) {
                Text("保存")
            }
        },
        dismissButton = {
            OutlinedButton(onClick = onDismiss) {
                Text("取消")
            }
        }
    )
}

@Composable
private fun EditableSettingsRow(
    title: String,
    value: String,
    tag: String,
    onClick: () -> Unit
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .height(52.dp)
            .clickable(onClick = onClick)
            .testTag(tag),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            title,
            color = Ink,
            fontSize = 22.sp,
            modifier = Modifier.weight(0.42f)
        )
        Text(
            "$value  ›",
            color = Muted,
            fontSize = 22.sp,
            modifier = Modifier.weight(0.58f),
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            textAlign = TextAlign.End
        )
    }
}

@Composable
private fun StaticSettingsRow(
    title: String,
    value: String,
    tag: String,
    showChevron: Boolean = true
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .height(52.dp)
            .testTag(tag),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            title,
            color = Ink,
            fontSize = 22.sp,
            modifier = Modifier.weight(0.42f)
        )
        Text(
            if (showChevron) "$value  ›" else value,
            color = Muted,
            fontSize = 22.sp,
            modifier = Modifier.weight(0.58f),
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            textAlign = TextAlign.End
        )
    }
}

@Composable
private fun ToggleSettingsRow(
    title: String,
    checked: Boolean,
    tag: String,
    onCheckedChange: (Boolean) -> Unit
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .height(52.dp)
            .clickable { onCheckedChange(!checked) }
            .testTag(tag),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(title, color = Ink, fontSize = 22.sp)
        Switch(
            checked = checked,
            onCheckedChange = onCheckedChange,
            colors = SwitchDefaults.colors(
                checkedThumbColor = Color.White,
                checkedTrackColor = Ink,
                uncheckedThumbColor = Color.White,
                uncheckedTrackColor = Color(0xFFE0E0E0)
            )
        )
    }
}

@Composable
private fun PermissionRow(title: String, value: String, tag: String, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .height(52.dp)
            .clickable(onClick = onClick)
            .testTag(tag),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(title, color = Ink, fontSize = 22.sp)
        Text(
            value,
            color = Success,
            fontSize = 17.sp,
            modifier = Modifier
                .clip(RoundedCornerShape(4.dp))
                .background(Color(0xFFEAF8EF))
                .padding(horizontal = 10.dp, vertical = 5.dp)
        )
    }
}

@Composable
private fun ActionSettingsRow(title: String, icon: String, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .height(52.dp)
            .clickable(onClick = onClick),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(title, color = Ink, fontSize = 22.sp)
        Text(icon, color = Muted, fontSize = 26.sp)
    }
}

@Composable
private fun SettingsDivider() {
    HorizontalDivider(color = Hairline, modifier = Modifier.padding(start = 0.dp))
}

@Composable
private fun DeveloperDiagnosticsScreen(
    diagnostics: EdgeDiagnostics,
    useStableRuntime: Boolean,
    runtimeUrl: String,
    deviceId: String,
    edgeToken: String,
    onStableRuntimeChanged: (Boolean) -> Unit,
    onRuntimeUrlChanged: (String) -> Unit,
    onDeviceIdChanged: (String) -> Unit,
    onEdgeTokenChanged: (String) -> Unit,
    onSendObservations: () -> Unit,
    onTestNotification: () -> Unit,
    onTestUrgentAlert: () -> Unit
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(24.dp)
            .testTag(AndroidEdgeTestTags.DEVELOPER_DIAGNOSTICS_VIEW),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text("Developer Diagnostics", fontSize = 28.sp, color = Ink)
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text("Persistent Runtime", color = Ink)
            Switch(checked = useStableRuntime, onCheckedChange = onStableRuntimeChanged)
        }
        OutlinedTextField(
            modifier = Modifier.fillMaxWidth(),
            value = runtimeUrl,
            onValueChange = onRuntimeUrlChanged,
            label = { Text("Runtime WebSocket URL") }
        )
        OutlinedTextField(
            modifier = Modifier.fillMaxWidth(),
            value = deviceId,
            onValueChange = onDeviceIdChanged,
            label = { Text("Device ID") }
        )
        OutlinedTextField(
            modifier = Modifier.fillMaxWidth(),
            value = edgeToken,
            onValueChange = onEdgeTokenChanged,
            label = { Text("Edge Token") },
            visualTransformation = PasswordVisualTransformation()
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = onSendObservations) { Text("Send Observations") }
            OutlinedButton(onClick = onTestNotification) { Text("Test Notification") }
        }
        OutlinedButton(onClick = onTestUrgentAlert) { Text("Test Urgent Alert") }
        DiagnosticLine("Connection", diagnostics.connectionState)
        DiagnosticLine("Service", diagnostics.serviceState)
        DiagnosticLine("Runtime Mode", diagnostics.runtimeMode)
        DiagnosticLine("Reconnect", reconnectSummary(diagnostics))
        DiagnosticLine("Android Health", androidHealthSummary(LocalContext.current, diagnostics))
        DiagnosticLine("Screen Context", diagnostics.screenContextState)
        DiagnosticLine("Registered Capabilities", diagnostics.registeredCapabilities)
        DiagnosticLine("Recent Observations", diagnostics.recentObservations.ifBlank { "None yet" })
        DiagnosticLine("Recent Actions", diagnostics.recentActions.ifBlank { "None yet" })
        DiagnosticLine("Last Error", diagnostics.lastError.ifBlank { "None" })
        DiagnosticLine("Last Sent Frame", diagnostics.lastSentFrame.ifBlank { "None yet" })
        DiagnosticLine("Last Received Frame", diagnostics.lastReceivedFrame.ifBlank { "None yet" })
    }
}

@Composable
private fun DiagnosticLine(title: String, body: String) {
    Text("$title\n$body", color = Ink, fontSize = 14.sp)
}

@Composable
private fun BottomNav(selectedView: String, modifier: Modifier = Modifier, onSelect: (String) -> Unit) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 20.dp, vertical = 22.dp)
            .height(64.dp)
            .clip(RoundedCornerShape(36.dp))
            .background(Color.White)
            .border(1.dp, Hairline, RoundedCornerShape(36.dp))
            .padding(4.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        BottomNavItem(
            label = "连接",
            icon = "((•))",
            selected = selectedView == MainActivity.VIEW_CONNECT,
            tag = AndroidEdgeTestTags.CONNECT_TAB,
            modifier = Modifier.weight(1f)
        ) { onSelect(MainActivity.VIEW_CONNECT) }
        BottomNavItem(
            label = "聊天",
            icon = "○",
            selected = selectedView == MainActivity.VIEW_GLOBAL_CHAT,
            tag = AndroidEdgeTestTags.GLOBAL_CHAT_TAB,
            modifier = Modifier.weight(1f)
        ) { onSelect(MainActivity.VIEW_GLOBAL_CHAT) }
        BottomNavItem(
            label = "设置",
            icon = "≡",
            selected = selectedView == MainActivity.VIEW_SETTINGS,
            tag = AndroidEdgeTestTags.SETTINGS_TAB,
            modifier = Modifier.weight(1f)
        ) { onSelect(MainActivity.VIEW_SETTINGS) }
    }
}

@Composable
private fun BottomNavItem(
    label: String,
    icon: String,
    selected: Boolean,
    tag: String,
    modifier: Modifier = Modifier,
    onClick: () -> Unit
) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .clip(RoundedCornerShape(32.dp))
            .background(if (selected) Ink else Color.Transparent)
            .clickable(onClick = onClick)
            .testTag(tag),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Text(icon, color = if (selected) Color.White else Color(0xFFC4C4C4), fontSize = 18.sp)
        Text(label, color = if (selected) Color.White else Color(0xFFC4C4C4), fontSize = 15.sp)
    }
}

private fun openSettings(context: Context, intent: Intent) {
    context.startActivity(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
}

private fun startEdgeService(context: Context, intent: android.content.Intent) {
    if (intent.action == AndroidEdgeService.ACTION_STOP) {
        context.startService(intent)
    } else if (intent.action == AndroidEdgeService.ACTION_SUBMIT_TEXT) {
        context.startService(intent)
    } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
        context.startForegroundService(intent)
    } else {
        context.startService(intent)
    }
}

private fun saveConfig(
    context: Context,
    runtimeMode: String,
    runtimeUrl: String,
    deviceId: String,
    edgeToken: String
) {
    AndroidEdgePreferences.saveConfig(
        context,
        AndroidEdgeConfig(
            runtimeMode = runtimeMode,
            runtimeUrl = runtimeUrl,
            deviceId = deviceId,
            edgeToken = edgeToken
        )
    )
}

private fun productConnectionState(
    diagnostics: EdgeDiagnostics,
    runtimeUrl: String,
    notificationState: String
): String =
    when {
        runtimeUrl.isBlank() -> "needs_setup"
        notificationState == "denied" || notificationStateFromDiagnostics(diagnostics) == "denied" -> "restricted"
        diagnostics.reconnectStatus.startsWith("retrying") -> "reconnecting"
        diagnostics.connectionState == "connected" -> "connected"
        diagnostics.connectionState == "connecting" -> "connecting"
        diagnostics.lastError.isNotBlank() -> "error"
        else -> "disconnected"
    }

private fun normalizedSelectorState(state: String): String =
    when (state) {
        "needs_setup", "restricted" -> "disconnected"
        "reconnecting" -> "connecting"
        else -> state
    }

private fun connectionTitleZh(state: String): String =
    when (state) {
        "connected" -> "已连接"
        "connecting" -> "连接中"
        "reconnecting" -> "重新连接中"
        "restricted" -> "受限"
        "error" -> "错误"
        "needs_setup" -> "需要设置"
        else -> "已断开"
    }

private fun primaryActionLabel(state: String): String =
    when (state) {
        "connected" -> "connected"
        "connecting" -> "connecting"
        "reconnecting" -> "reconnect"
        "restricted" -> "restricted"
        "error" -> "retry"
        "needs_setup" -> "setup"
        else -> "connect"
    }

private fun statusDotColor(state: String): Color =
    when (state) {
        "connected" -> Success
        "error", "restricted" -> Danger
        "connecting", "reconnecting" -> Color(0xFFF4C542)
        else -> Muted
    }

private fun endpointSummary(runtimeUrl: String): String =
    runtimeUrl
        .removePrefix("ws://")
        .removePrefix("wss://")
        .substringBefore("/")
        .ifBlank { "runtime.local:8080" }

private fun connectionSubtitle(diagnostics: EdgeDiagnostics): String =
    when {
        diagnostics.connectionState == "connected" -> "延迟 12ms · 安全连接"
        diagnostics.lastError.isNotBlank() -> diagnostics.lastError.take(26)
        diagnostics.reconnectStatus.startsWith("retrying") -> diagnostics.reconnectStatus
        else -> "等待连接 · WebSocket"
    }

private fun notificationState(context: Context): String =
    if (RuntimeNotificationPresenter.canPostNotifications(context)) "granted" else "denied"

private fun notificationStateFromDiagnostics(diagnostics: EdgeDiagnostics): String =
    diagnostics.notificationHealth.ifBlank { "granted" }

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
        }}",
        "background_observation=${diagnostics.backgroundObservationState}",
        "last_local_observation=${diagnostics.lastLocalObservationAt.ifBlank { "never" }}",
        "last_successful_upload=${diagnostics.lastSuccessfulUploadAt.ifBlank { "never" }}",
        "delivery_queue_depth=${diagnostics.deliveryQueueDepth}",
        "background_guidance=${AndroidEdgeHealth.backgroundPermissionGuidance(
            batteryState = diagnostics.batteryHealth.ifBlank {
                AndroidEdgeHealth.batteryOptimizationState(context)
            }
        )}",
        "accessibility=${AndroidEdgeHealth.accessibilityServiceState(context)}",
        "screen_context=${diagnostics.screenContextState.ifBlank {
            if (AndroidEdgePreferences.screenContextObservationEnabled(context)) "enabled" else "disabled"
        }}"
    ).joinToString("\n")

@Preview(showBackground = true)
@Composable
fun M17BootstrapScreenPreview() {
    OpenHaloAndroidEdgeTheme {
        M17BootstrapScreen()
    }
}
