package pe.profejohnny.mathbattle.game

import kotlin.math.max
import kotlin.math.min
import kotlin.random.Random

data class LevelRule(
    val id: Int,
    val name: String,
    val skill: String,
    val capSeconds: Double,
    val gainSeconds: Double,
    val lossSeconds: Double,
    val target: Int?
)

data class MathQuestion(
    val text: String,
    val answer: Int,
    val choices: List<Int>,
    val explanation: String,
    val level: Int
)

object GameEngine {
    val levels = listOf(
        LevelRule(1, "El despertar", "Sumas y restas", 10.0, 1.5, 1.0, 30),
        LevelRule(2, "El desafío", "Potencias de 2", 12.0, 2.0, 1.5, 50),
        LevelRule(3, "La batalla infinita", "Operaciones combinadas", 15.0, 3.0, 2.0, null)
    )

    fun levelFor(score: Int) = when {
        score < 30 -> 1
        score < 50 -> 2
        else -> 3
    }

    fun timeAfter(remaining: Double, correct: Boolean, level: Int, multiplier: Double = 1.0): Double {
        val rule = levels[level - 1]
        val delta = if (correct) rule.gainSeconds else -rule.lossSeconds
        return max(0.0, min(rule.capSeconds * multiplier, remaining + delta * multiplier))
    }

    fun question(score: Int = 0, random: Random = Random.Default): MathQuestion {
        fun int(a: Int, b: Int) = random.nextInt(a, b + 1)
        val superscript = listOf('⁰', '¹', '²', '³', '⁴', '⁵', '⁶', '⁷', '⁸', '⁹')
        val level = levelFor(score)
        var text: String
        var answer: Int
        var explanation: String
        val wrong = mutableListOf<Int>()

        if (level == 1) {
            val addition = random.nextBoolean()
            val a: Int
            val b: Int
            if (score < 10) {
                if (addition) {
                    a = int(1, 9); b = int(1, 9)
                } else {
                    a = int(2, 9); b = int(1, a - 1)
                }
            } else if (score < 20) {
                a = int(10, 99); b = int(1, 9)
            } else {
                a = int(100, 499); b = int(1, 9)
            }
            if (addition) {
                answer = a + b; text = "$a + $b"; wrong += listOf(answer + 10, answer - 1)
            } else {
                answer = a - b; text = "$a − $b"; wrong += listOf(answer + 1, answer + 10)
            }
            explanation = "$text = $answer."
        } else if (level == 2) {
            val n = int(1, 9)
            val b = int(1, 9)
            val power = 1 shl n
            answer = power + b
            text = "2${superscript[n]} + $b"
            wrong += listOf(2 * n + b, power - b, power + b + int(1, 5))
            explanation = "2 elevado a $n es $power. Luego $power + $b = $answer."
        } else {
            var a = int(2, 12)
            val b = int(2, 9)
            var c = int(2, 9)
            when (int(0, if (score >= 60) 5 else 3)) {
                0 -> { answer = a + b * c; text = "$a + $b × $c"; wrong += listOf((a + b) * c, a + b + c); explanation = "Primero $b × $c = ${b * c}. Después $a + ${b * c} = $answer." }
                1 -> { a = b * c + int(1, 25); answer = a - b * c; text = "$a − $b × $c"; wrong += listOf((a - b) * c, a - b - c); explanation = "Primero $b × $c = ${b * c}. Después $a − ${b * c} = $answer." }
                2 -> { answer = a + c; text = "${a * b} ÷ $b + $c"; wrong += listOf(a - c, a * b + c); explanation = "Primero ${a * b} ÷ $b = $a. Después $a + $c = $answer." }
                3 -> { answer = a + b; text = "$a + ${b * c} ÷ $c"; wrong += listOf(a + b * c, a + b + c); explanation = "Primero ${b * c} ÷ $c = $b. Después $a + $b = $answer." }
                4 -> { answer = (a + b) * c; text = "($a + $b) × $c"; wrong += listOf(a + b * c, a + b + c); explanation = "Primero el paréntesis: $a + $b = ${a + b}. Después ${a + b} × $c = $answer." }
                else -> { c = min(c, a * b - 1); answer = a * b - c; text = "$a × $b − $c"; wrong += listOf(a * (b - c), a * b + c); explanation = "Primero $a × $b = ${a * b}. Después ${a * b} − $c = $answer." }
            }
        }

        val choices = mutableListOf(answer)
        wrong.shuffled(random).forEach { if (it > 0 && it !in choices && choices.size < 3) choices += it }
        var step = 1
        while (choices.size < 3) if (answer + step !in choices) choices += answer + step++ else step++
        return MathQuestion(text, answer, choices.shuffled(random), explanation, level)
    }
}
