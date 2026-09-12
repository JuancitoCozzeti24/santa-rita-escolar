package pe.profejohnny.mathbattle.auth

import android.app.Activity
import androidx.credentials.CredentialManager
import androidx.credentials.GetCredentialRequest
import com.google.android.libraries.identity.googleid.GetGoogleIdOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.auth.GoogleAuthProvider
import kotlinx.coroutines.tasks.await
import pe.profejohnny.mathbattle.BuildConfig

class GoogleAuthManager(private val activity: Activity) {
    suspend fun signIn(): Result<Unit> = runCatching {
        require(BuildConfig.WEB_CLIENT_ID.isNotBlank()) { "Firebase todavía no está configurado" }
        val option = GetGoogleIdOption.Builder()
            .setFilterByAuthorizedAccounts(false)
            .setServerClientId(BuildConfig.WEB_CLIENT_ID)
            .setAutoSelectEnabled(false)
            .build()
        val request = GetCredentialRequest.Builder().addCredentialOption(option).build()
        val credential = CredentialManager.create(activity).getCredential(activity, request).credential
        val google = GoogleIdTokenCredential.createFrom(credential.data)
        FirebaseAuth.getInstance().signInWithCredential(
            GoogleAuthProvider.getCredential(google.idToken, null)
        ).await()
    }
}
