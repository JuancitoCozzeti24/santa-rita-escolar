package pe.profejohnny.mathbattle.game

import kotlin.random.Random
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class GameEngineTest {
    @Test fun levelsMatchNewProgression() {
        assertEquals(1, GameEngine.levelFor(0))
        assertEquals(1, GameEngine.levelFor(9))
        assertEquals(2, GameEngine.levelFor(10))
        assertEquals(3, GameEngine.levelFor(20))
        assertEquals(4, GameEngine.levelFor(30))
        assertEquals(6, GameEngine.levelFor(50))
        assertEquals(8, GameEngine.levelFor(70))
        assertEquals(10, GameEngine.levelFor(90))
        assertEquals(11, GameEngine.levelFor(100))
        assertEquals(11, GameEngine.levelFor(119))
    }

    @Test fun timerIsAlwaysClamped() {
        assertEquals(10.0, GameEngine.timeAfter(9.5, true, 1), 0.001)
        assertEquals(0.0, GameEngine.timeAfter(0.4, false, 1), 0.001)
    }

    @Test fun generatedQuestionsContainOneCorrectChoice() {
        for (score in listOf(0, 9, 10, 19, 20, 29, 30, 39, 40, 49, 50, 59, 60, 69, 70, 79, 80, 89, 90, 99, 100, 119)) {
            repeat(100) {
                val q = GameEngine.question(score, Random(score * 1000 + it))
                assertEquals(3, q.choices.distinct().size)
                assertEquals(1, q.choices.count { choice -> choice == q.answer })
                assertTrue(q.choices.all(String::isNotBlank))
            }
        }
    }

    @Test fun milestonePausesAreAtTheRequestedScores() {
        assertEquals(null, GameEngine.milestoneFor(10))
        assertEquals(30, GameEngine.milestoneFor(30)?.score)
        assertEquals(60, GameEngine.milestoneFor(60)?.score)
        assertEquals(80, GameEngine.milestoneFor(80)?.score)
        assertEquals(true, GameEngine.milestoneFor(120)?.final)
    }
}
