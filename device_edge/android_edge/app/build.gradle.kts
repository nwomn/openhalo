import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
}

val localProperties = Properties().apply {
    val file = rootProject.file("local.properties")
    if (file.exists()) {
        file.inputStream().use(::load)
    }
}

fun localProperty(name: String, defaultValue: String): String =
    localProperties.getProperty(name)?.takeIf { it.isNotBlank() } ?: defaultValue

android {
    namespace = "dev.openhalo.android.edge"
    compileSdk {
        version = release(36) {
            minorApiLevel = 1
        }
    }

    defaultConfig {
        applicationId = "dev.openhalo.android.edge"
        minSdk = 24
        targetSdk = 36
        versionCode = 1
        versionName = "1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        buildConfigField(
            "String",
            "OPENHALO_DEV_RUNTIME_URL",
            "\"${localProperty("openhalo.devRuntimeUrl", "")}\""
        )
        buildConfigField(
            "String",
            "OPENHALO_DEV_EDGE_TOKEN",
            "\"${localProperty("openhalo.devEdgeToken", "")}\""
        )
        buildConfigField(
            "String",
            "OPENHALO_STABLE_RUNTIME_URL",
            "\"${localProperty("openhalo.stableRuntimeUrl", "")}\""
        )
        buildConfigField(
            "String",
            "OPENHALO_STABLE_EDGE_TOKEN",
            "\"${localProperty("openhalo.stableEdgeToken", "")}\""
        )
    }

    buildTypes {
        release {
            optimization {
                enable = false
            }
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
}

dependencies {
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.graphics)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.okhttp)
    testImplementation(libs.junit)
    testImplementation(libs.json)
    androidTestImplementation(platform(libs.androidx.compose.bom))
    androidTestImplementation(libs.androidx.compose.ui.test.junit4)
    androidTestImplementation(libs.androidx.espresso.core)
    androidTestImplementation(libs.androidx.junit)
    debugImplementation(libs.androidx.compose.ui.test.manifest)
    debugImplementation(libs.androidx.compose.ui.tooling)
}
