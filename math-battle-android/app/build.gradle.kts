import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

val local = Properties().apply {
    val file = rootProject.file("local.properties")
    if (file.exists()) file.inputStream().use(::load)
}

val firebaseDefaults = mapOf(
    "FIREBASE_APPLICATION_ID" to "1:562272595963:android:65d896db19bbd969f7655e",
    "FIREBASE_API_KEY" to "AIzaSyD15VjkrpLW5sroikO8enlnRNiOIMCNFjU",
    "FIREBASE_PROJECT_ID" to "math-battle-63367",
    "FIREBASE_STORAGE_BUCKET" to "math-battle-63367.firebasestorage.app",
    "WEB_CLIENT_ID" to "562272595963-vpn1oans4nl0o27ebhblkt5pgbdl4b61.apps.googleusercontent.com",
)

fun configured(name: String): String =
    (System.getenv(name).takeUnless { it.isNullOrBlank() }
        ?: local.getProperty(name).takeUnless { it.isNullOrBlank() }
        ?: firebaseDefaults[name]
        ?: "")
        .replace("\\", "\\\\").replace("\"", "\\\"")

android {
    namespace = "pe.profejohnny.mathbattle"
    compileSdk = 35

    defaultConfig {
        applicationId = "pe.profejohnny.mathbattle"
        minSdk = 26
        targetSdk = 35
        versionCode = 9
        versionName = "1.0.8"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        vectorDrawables.useSupportLibrary = true

        buildConfigField("String", "FIREBASE_APPLICATION_ID", "\"${configured("FIREBASE_APPLICATION_ID")}\"")
        buildConfigField("String", "FIREBASE_API_KEY", "\"${configured("FIREBASE_API_KEY")}\"")
        buildConfigField("String", "FIREBASE_PROJECT_ID", "\"${configured("FIREBASE_PROJECT_ID")}\"")
        buildConfigField("String", "FIREBASE_STORAGE_BUCKET", "\"${configured("FIREBASE_STORAGE_BUCKET")}\"")
        buildConfigField("String", "WEB_CLIENT_ID", "\"${configured("WEB_CLIENT_ID")}\"")
    }

    signingConfigs {
        create("release") {
            val path = System.getenv("MATH_BATTLE_KEYSTORE")
            if (!path.isNullOrBlank()) {
                storeFile = file(path)
                storePassword = System.getenv("MATH_BATTLE_STORE_PASSWORD")
                keyAlias = System.getenv("MATH_BATTLE_KEY_ALIAS")
                keyPassword = System.getenv("MATH_BATTLE_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        debug {
            versionNameSuffix = "-debug"
        }
        release {
            // Esta app se distribuye directamente por APK. Mantener Credential Manager
            // sin ofuscación evita diferencias entre la compilación de prueba y la final.
            isMinifyEnabled = false
            isShrinkResources = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            if (!System.getenv("MATH_BATTLE_KEYSTORE").isNullOrBlank()) signingConfig = signingConfigs.getByName("release")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions.jvmTarget = "17"
    buildFeatures {
        compose = true
        buildConfig = true
    }
    packaging.resources.excludes += "/META-INF/{AL2.0,LGPL2.1}"
}

dependencies {
    implementation(platform("androidx.compose:compose-bom:2024.12.01"))
    implementation("androidx.activity:activity-compose:1.10.0")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-play-services:1.10.1")
    implementation("androidx.navigation:navigation-compose:2.8.5")
    implementation("com.google.android.gms:play-services-auth:21.3.0")
    implementation(platform("com.google.firebase:firebase-bom:33.8.0"))
    implementation("com.google.firebase:firebase-auth")
    implementation("com.google.firebase:firebase-firestore")
    implementation("com.google.firebase:firebase-appcheck-playintegrity")
    debugImplementation("com.google.firebase:firebase-appcheck-debug")
    implementation("androidx.media3:media3-exoplayer:1.5.1")
    implementation("androidx.media3:media3-ui:1.5.1")
    testImplementation("junit:junit:4.13.2")
    debugImplementation("androidx.compose.ui:ui-tooling")
}
