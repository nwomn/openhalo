package dev.openhalo.android.edge

import android.os.Bundle
import android.content.Intent
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import dev.openhalo.android.edge.ui.theme.OpenHaloAndroidEdgeTheme

class RuntimeAlertActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val message = intent.getStringExtra(EXTRA_MESSAGE).orEmpty()
            .ifBlank { "OpenHalo alert" }
        setContent {
            OpenHaloAndroidEdgeTheme {
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(32.dp),
                    verticalArrangement = Arrangement.spacedBy(24.dp)
                ) {
                    Text(
                        text = "OpenHalo Alert",
                        style = MaterialTheme.typography.headlineMedium
                    )
                    Text(
                        text = message,
                        style = MaterialTheme.typography.bodyLarge
                    )
                    Button(onClick = { finish() }) {
                        Text("Dismiss")
                    }
                    Button(
                        onClick = {
                            startActivity(
                                Intent(this@RuntimeAlertActivity, MainActivity::class.java)
                                    .putExtra(
                                        MainActivity.EXTRA_INITIAL_VIEW,
                                        MainActivity.VIEW_NOTIFICATIONS
                                    )
                            )
                            finish()
                        }
                    ) {
                        Text("Open Details")
                    }
                }
            }
        }
    }

    companion object {
        const val EXTRA_MESSAGE = "dev.openhalo.android.edge.extra.ALERT_MESSAGE"
    }
}
