package pe.profejohnny.mathbattle.game

import kotlin.random.Random
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class GameEngineTest {
    @Test fun levelsMatchOriginalThresholds() {
        assertEquals(1, GameEngine.levelFor(0))
        assertEquals(1, GameEngine.levelFor(29))
        assertEquals(2, GameEngine.levelFor(30))
        assertEquals(2, GameEngine.levelFor(49))
        assertEquals(3, GameEngine.levelFor(50))
    }

    @Test fun timerIsAlwaysClamped() {
        assertEquals(10.0, GameEngine.timeAfter(9.5, true, 1), 0.001)
        assertEquals(0.0, GameEngine.timeAfter(0.4, false, 1), 0.001)
    }

    @Test fun generatedQuestionsContainOneCorrectChoice() {
        for (score in listOf(0, 9, 10, 19, 20, 29, 30, 49, 50, 80)) {
            repeat(100) {
                val q = GameEngine.question(score, Random(score * 1000 + it))
                assertEquals(3, q.choices.distinct().size)
                assertEquals(1, q.choices.count { choice -> choice == q.answer })
                assertTrue(q.choices.all { choice -> choice > 0 })
            }
        }
    }
}
