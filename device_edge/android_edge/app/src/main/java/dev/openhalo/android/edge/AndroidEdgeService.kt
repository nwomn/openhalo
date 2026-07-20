package dev.openhalo.android.edge

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.util.Log
import androidx.core.app.NotificationCompat

class AndroidEdgeService : Service() {
    private var client: AndroidEdgeClient? = null
    private var foregroundStarted = false
    private val backgroundObservationHandler = Handler(Looper.getMainLooper())
    private val backgroundObservationTick = object : Runnable {
        override fun run() {
            if (!AndroidEdgePreferences.backgroundKeepAliveEnabled(applicationContext)) {
                EdgeDiagnosticsStore.update(
                    EdgeDiagnosticsStore.current().copy(
                        backgroundObservationState = "disabled by user"
                    )
                )
                return
            }
            val uploaded = client?.sendCurrentObservations(appVisibility = "background") == true
            val current = EdgeDiagnosticsStore.current()
            EdgeDiagnosticsStore.update(
                current.copy(
                    serviceState = "foreground",
                    backgroundObservationState = if (uploaded) {
                        "heartbeat uploaded"
                    } else {
                        "heartbeat queued: websocket disconnected"
                    }
                )
            )
            backgroundObservationHandler.postDelayed(
                this,
                backgroundObservationIntervalMillis()
            )
        }
    }

    override fun onCreate() {
        super.onCreate()
        ensureServiceNotificationChannel()
        client = AndroidEdgeClient(
            context = applicationContext,
            initialState = EdgeDiagnosticsStore.current()
        ) { next ->
            EdgeDiagnosticsStore.update(next.copy(serviceState = "foreground"))
        }
        ScreenContextObservationBridge.attach { observation ->
            client?.sendScreenContextObservation(observation)
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action ?: ACTION_START) {
            ACTION_START -> {
                startAsForegroundService()
                val storedConfig = AndroidEdgePreferences.loadConfig(applicationContext)
                val runtimeMode = intent?.getStringExtra(EXTRA_RUNTIME_MODE)
                    ?: storedConfig.runtimeMode
                val runtimeUrl = intent?.getStringExtra(EXTRA_RUNTIME_URL)
                    ?: storedConfig.runtimeUrl
                val deviceId = intent?.getStringExtra(EXTRA_DEVICE_ID)
                    ?: storedConfig.deviceId
                val edgeToken = intent?.getStringExtra(EXTRA_EDGE_TOKEN)
                    ?: storedConfig.edgeToken
                val pairingCode = intent?.getStringExtra(EXTRA_PAIRING_CODE).orEmpty()
                Log.i(LOG_TAG, "OPENHALO_EDGE_EVENT {\"event\":\"service_start_requested\"}")
                client?.connect(runtimeMode, runtimeUrl, deviceId, edgeToken, pairingCode)
                scheduleBackgroundObservationHeartbeat()
            }

            ACTION_SEND_OBSERVATIONS -> {
                startAsForegroundService()
                Log.i(LOG_TAG, "OPENHALO_EDGE_EVENT {\"event\":\"service_observation_requested\"}")
                client?.sendCurrentObservations()
                scheduleBackgroundObservationHeartbeat()
            }

            ACTION_SUBMIT_TEXT -> {
                startAsForegroundService()
                val text = intent?.getStringExtra(EXTRA_TEXT_COMMAND).orEmpty()
                Log.i(LOG_TAG, "OPENHALO_EDGE_EVENT {\"event\":\"service_text_submitted\"}")
                client?.submitTextCommand(text)
            }

            ACTION_STOP -> {
                Log.i(LOG_TAG, "OPENHALO_EDGE_EVENT {\"event\":\"service_stop_requested\"}")
                client?.disconnect()
                EdgeDiagnosticsStore.update(
                    EdgeDiagnosticsStore.current().copy(
                        serviceState = "stopped",
                        backgroundObservationState = "stopped"
                    )
                )
                backgroundObservationHandler.removeCallbacksAndMessages(null)
                stopForeground(STOP_FOREGROUND_REMOVE)
                foregroundStarted = false
                stopSelf()
            }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        client?.disconnect()
        client = null
        backgroundObservationHandler.removeCallbacksAndMessages(null)
        ScreenContextObservationBridge.detach()
        EdgeDiagnosticsStore.update(
            EdgeDiagnosticsStore.current().copy(
                serviceState = "stopped",
                backgroundObservationState = "stopped"
            )
        )
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun startAsForegroundService() {
        if (foregroundStarted) {
            EdgeDiagnosticsStore.update(
                EdgeDiagnosticsStore.current().copy(serviceState = "foreground")
            )
            return
        }
        val notification = serviceNotification()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(
                SERVICE_NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
            )
        } else {
            startForeground(SERVICE_NOTIFICATION_ID, notification)
        }
        EdgeDiagnosticsStore.update(
            EdgeDiagnosticsStore.current().copy(
                serviceState = "foreground",
                backgroundObservationState = if (
                    AndroidEdgePreferences.backgroundKeepAliveEnabled(applicationContext)
                ) {
                    "foreground service active"
                } else {
                    "disabled by user"
                }
            )
        )
        foregroundStarted = true
    }

    private fun scheduleBackgroundObservationHeartbeat() {
        backgroundObservationHandler.removeCallbacksAndMessages(null)
        if (!AndroidEdgePreferences.backgroundKeepAliveEnabled(applicationContext)) {
            EdgeDiagnosticsStore.update(
                EdgeDiagnosticsStore.current().copy(
                    backgroundObservationState = "disabled by user"
                )
            )
            return
        }
        EdgeDiagnosticsStore.update(
            EdgeDiagnosticsStore.current().copy(
                serviceState = "foreground",
                backgroundObservationState = "heartbeat scheduled"
            )
        )
        backgroundObservationHandler.postDelayed(
            backgroundObservationTick,
            backgroundObservationIntervalMillis()
        )
    }

    private fun serviceNotification(): Notification {
        val activityIntent = Intent(this, MainActivity::class.java)
        val pendingIntent = PendingIntent.getActivity(
            this,
            0,
            activityIntent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        return NotificationCompat.Builder(this, SERVICE_CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle("OpenHalo Android Edge")
            .setContentText("Background observation and edge session are active")
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setSilent(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()
    }

    private fun ensureServiceNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            return
        }
        val channel = NotificationChannel(
            SERVICE_CHANNEL_ID,
            "OpenHalo edge service",
            NotificationManager.IMPORTANCE_LOW
        )
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }

    companion object {
        const val ACTION_START = "dev.openhalo.android.edge.action.START"
        const val ACTION_STOP = "dev.openhalo.android.edge.action.STOP"
        const val ACTION_SEND_OBSERVATIONS =
            "dev.openhalo.android.edge.action.SEND_OBSERVATIONS"
        const val ACTION_SUBMIT_TEXT = "dev.openhalo.android.edge.action.SUBMIT_TEXT"
        const val EXTRA_RUNTIME_MODE = "runtime_mode"
        const val EXTRA_RUNTIME_URL = "runtime_url"
        const val EXTRA_DEVICE_ID = "device_id"
        const val EXTRA_EDGE_TOKEN = "edge_token"
        const val EXTRA_PAIRING_CODE = "pairing_code"
        const val EXTRA_TEXT_COMMAND = "text_command"
        private const val SERVICE_CHANNEL_ID = "openhalo_edge_service"
        private const val SERVICE_NOTIFICATION_ID = 1702
        private const val LOG_TAG = "OpenHaloEdge"

        fun startIntent(
            context: Context,
            runtimeMode: String,
            runtimeUrl: String,
            deviceId: String,
            edgeToken: String,
            pairingCode: String = ""
        ): Intent =
            Intent(context, AndroidEdgeService::class.java).apply {
                action = ACTION_START
                putExtra(EXTRA_RUNTIME_MODE, runtimeMode)
                putExtra(EXTRA_RUNTIME_URL, runtimeUrl)
                putExtra(EXTRA_DEVICE_ID, deviceId)
                putExtra(EXTRA_EDGE_TOKEN, edgeToken)
                if (pairingCode.isNotBlank()) {
                    putExtra(EXTRA_PAIRING_CODE, pairingCode)
                }
            }

        fun sendObservationsIntent(context: Context): Intent =
            Intent(context, AndroidEdgeService::class.java).apply {
                action = ACTION_SEND_OBSERVATIONS
            }

        fun submitTextIntent(context: Context, text: String): Intent =
            Intent(context, AndroidEdgeService::class.java).apply {
                action = ACTION_SUBMIT_TEXT
                putExtra(EXTRA_TEXT_COMMAND, text)
            }

        fun stopIntent(context: Context): Intent =
            Intent(context, AndroidEdgeService::class.java).apply {
                action = ACTION_STOP
            }
    }
}

fun backgroundObservationIntervalMillis(): Long = 60_000L
