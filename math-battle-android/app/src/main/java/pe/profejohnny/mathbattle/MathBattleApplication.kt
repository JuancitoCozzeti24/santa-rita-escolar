package pe.profejohnny.mathbattle

import android.app.Application
import com.google.firebase.FirebaseApp
import com.google.firebase.FirebaseOptions
import com.google.firebase.appcheck.FirebaseAppCheck

class MathBattleApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        if (!isFirebaseConfigured()) return

        val options = FirebaseOptions.Builder()
            .setApplicationId(BuildConfig.FIREBASE_APPLICATION_ID)
            .setApiKey(BuildConfig.FIREBASE_API_KEY)
            .setProjectId(BuildConfig.FIREBASE_PROJECT_ID)
            .setStorageBucket(BuildConfig.FIREBASE_STORAGE_BUCKET)
            .build()
        if (FirebaseApp.getApps(this).isEmpty()) FirebaseApp.initializeApp(this, options)

        FirebaseAppCheck.getInstance().installAppCheckProviderFactory(appCheckProviderFactory())
    }

    companion object {
        fun isFirebaseConfigured() = BuildConfig.FIREBASE_APPLICATION_ID.isNotBlank() &&
            BuildConfig.FIREBASE_API_KEY.isNotBlank() && BuildConfig.FIREBASE_PROJECT_ID.isNotBlank() &&
            BuildConfig.WEB_CLIENT_ID.isNotBlank()
    }
}
