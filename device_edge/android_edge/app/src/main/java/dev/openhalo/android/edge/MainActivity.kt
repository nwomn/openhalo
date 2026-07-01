package dev.openhalo.android.edge

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
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
    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(horizontal = 24.dp, vertical = 32.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Text(
            text = "OpenHalo Android Edge",
            style = MaterialTheme.typography.headlineMedium
        )
        Text(
            text = "M17 bootstrap project is ready for the first native Android device edge slice.",
            style = MaterialTheme.typography.bodyLarge
        )
        Text(
            text = "Planned first capabilities:",
            style = MaterialTheme.typography.titleMedium
        )
        Text(
            text = "mobile.context\nmobile.input\nnotification.show\nmobile.reply.render\nmobile.prompt_user",
            style = MaterialTheme.typography.bodyMedium
        )
        Text(
            text = "Next implementation focus: diagnostics surface, Edge API session link, and background service lifecycle.",
            style = MaterialTheme.typography.bodyMedium
        )
    }
}

@Preview(showBackground = true)
@Composable
fun M17BootstrapScreenPreview() {
    OpenHaloAndroidEdgeTheme {
        M17BootstrapScreen()
    }
}
