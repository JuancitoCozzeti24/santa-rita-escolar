package pe.profejohnny.mathbattle.auth

import android.app.Activity
import android.content.Intent
import com.google.android.gms.auth.api.signin.GoogleSignIn
import com.google.android.gms.auth.api.signin.GoogleSignInOptions
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.auth.GoogleAuthProvider
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.withTimeout
import pe.profejohnny.mathbattle.BuildConfig

/**
 * Explicit Google account flow for APKs distributed outside Google Play.
 * It launches Google's own account picker instead of waiting for a credential provider.
 */
class GoogleAuthManager(private val activity: Activity) {
    private val client by lazy {
        val options = GoogleSignInOptions.Builder(GoogleSignInOptions.DEFAULT_SIGN_IN)
            .requestIdToken(BuildConfig.WEB_CLIENT_ID)
            .requestEmail()
            .build()
        GoogleSignIn.getClient(activity, options)
    }

    fun signInIntent(): Intent = client.signInIntent

    suspend fun completeSignIn(data: Intent?): Result<Unit> = runCatching {
        require(BuildConfig.WEB_CLIENT_ID.isNotBlank()) { "Firebase todavía no está configurado" }
        val account = withTimeout(15_000) {
            GoogleSignIn.getSignedInAccountFromIntent(data).await()
        }
        val token = requireNotNull(account.idToken) { "Google no devolvió una credencial válida" }
        withTimeout(15_000) {
            FirebaseAuth.getInstance().signInWithCredential(
                GoogleAuthProvider.getCredential(token, null)
            ).await()
        }
    }
}
