package pe.profejohnny.mathbattle

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import pe.profejohnny.mathbattle.ui.MathBattleApp
import pe.profejohnny.mathbattle.ui.MathBattleViewModel
import pe.profejohnny.mathbattle.ui.MathBattleViewModelFactory

class MainActivity : ComponentActivity() {
    private val viewModel: MathBattleViewModel by viewModels {
        MathBattleViewModelFactory(MathBattleApplication.isFirebaseConfigured())
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        WindowCompat.setDecorFitsSystemWindows(window, false)
        enterImmersiveMode()
        setContent { MathBattleApp(viewModel) }
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) enterImmersiveMode()
    }

    override fun onResume() {
        super.onResume()
        enterImmersiveMode()
    }

    private fun enterImmersiveMode() {
        WindowInsetsControllerCompat(window, window.decorView).apply {
            hide(WindowInsetsCompat.Type.systemBars())
            systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        }
    }

    override fun onPause() {
        viewModel.onAppPaused()
        super.onPause()
    }
}
