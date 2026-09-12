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
    val target: Int
)

data class MathQuestion(
    val text: String,
    val answer: String,
    val choices: List<String>,
    val explanation: String,
    val level: Int
)

data class BattleMilestone(
    val score: Int,
    val eyebrow: String,
    val title: String,
    val message: String,
    val countdownLabel: String,
    val button: String,
    val final: Boolean = false
)

object GameEngine {
    val levels = listOf(
        LevelRule(1, "Calentamiento", "Sumas de una cifra", 10.0, 1.5, 1.0, 10),
        LevelRule(2, "Mente rápida", "Dos cifras con una cifra", 10.0, 1.5, 1.0, 20),
        LevelRule(3, "Primer desafío", "Dos cifras con dos cifras", 11.0, 1.5, 1.0, 30),
        LevelRule(4, "Tablas esenciales", "Multiplicaciones de una cifra", 11.0, 1.5, 1.0, 40),
        LevelRule(5, "Producto veloz", "Dos cifras por una cifra", 12.0, 1.5, 1.0, 50),
        LevelRule(6, "Maestro de tablas", "Productos hasta 19 × 19", 13.0, 1.5, 1.0, 60),
        LevelRule(7, "Operaciones combinadas", "Jerarquía de operaciones", 14.0, 1.5, 1.5, 70),
        LevelRule(8, "Poder matemático", "Potencias, divisiones y raíces", 15.0, 1.5, 1.5, 80),
        LevelRule(9, "Ligas mayores", "Ecuaciones básicas", 16.0, 1.5, 1.5, 90),
        LevelRule(10, "Factor común", "Razonamiento algebraico", 17.0, 1.5, 1.5, 100),
        LevelRule(11, "Lenguaje algebraico", "Traducción de expresiones", 18.0, 1.5, 1.5, 120)
    )

    private val milestones = listOf(
        BattleMilestone(30, "30 PUNTOS SUPERADOS", "¡Primer desafío completado!", "Has superado los 30 puntos. ¿Estás listo para 10 puntos más?", "PREPÁRATE PARA LAS MULTIPLICACIONES", "¡ESTOY LISTO!"),
        BattleMilestone(60, "CAMPEÓN DE LO ESENCIAL", "¡Dominaste las bases!", "Hasta el momento eres un campeón en esta primera etapa. ¿Estás listo para las operaciones combinadas?", "PREPÁRATE PARA COMBINAR OPERACIONES", "¡VAMOS!"),
        BattleMilestone(80, "GRAN LOGRO", "¡Agilidad matemática extraordinaria!", "Tu rapidez, precisión y dominio matemático te llevan a las ligas mayores.", "ENTRANDO A LAS LIGAS MAYORES", "¡ACEPTO EL RETO!"),
        BattleMilestone(120, "PRIMERA FASE COMPLETADA", "¡Has campeonado!", "Recibirás un premio. Pero esto no termina aquí… espera la segunda parte.", "CONTINUARÁ…", "DESCUBRIR QUÉ SIGUE", final = true)
    )

    fun levelFor(score: Int): Int = when {
        score < 10 -> 1
        score < 20 -> 2
        score < 30 -> 3
        score < 40 -> 4
        score < 50 -> 5
        score < 60 -> 6
        score < 70 -> 7
        score < 80 -> 8
        score < 90 -> 9
        score < 100 -> 10
        else -> 11
    }

    fun milestoneFor(score: Int): BattleMilestone? = milestones.firstOrNull { it.score == score }

    fun timeAfter(remaining: Double, correct: Boolean, level: Int): Double {
        val rule = levels[level - 1]
        val delta = if (correct) rule.gainSeconds else -rule.lossSeconds
        return max(0.0, min(rule.capSeconds, remaining + delta))
    }

    fun question(score: Int = 0, random: Random = Random.Default): MathQuestion {
        fun int(a: Int, b: Int) = random.nextInt(a, b + 1)
        val superscript = listOf('⁰', '¹', '²', '³', '⁴', '⁵', '⁶', '⁷', '⁸', '⁹')
        val level = levelFor(score)
        var text: String
        var answerValue: Int
        var explanation: String

        when (level) {
            1 -> {
                val a = int(1, 9); val b = int(1, 9)
                answerValue = a + b; text = "$a + $b"; explanation = "$a + $b = $answerValue."
            }
            2 -> {
                val addition = random.nextBoolean(); val a = int(10, 99); val b = int(1, 9)
                answerValue = if (addition) a + b else a - b
                text = "$a ${if (addition) "+" else "−"} $b"; explanation = "$text = $answerValue."
            }
            3 -> {
                val addition = random.nextBoolean(); var a = int(10, 99); var b = int(10, 99)
                if (!addition && b > a) { val temporary = a; a = b; b = temporary }
                answerValue = if (addition) a + b else a - b
                text = "$a ${if (addition) "+" else "−"} $b"; explanation = "$text = $answerValue."
            }
            4 -> {
                val a = int(2, 9); val b = int(2, 9)
                answerValue = a * b; text = "$a × $b"; explanation = "$a por $b es $answerValue."
            }
            5 -> {
                val a = int(10, 19); val b = int(2, 9)
                answerValue = a * b; text = "$a × $b"; explanation = "$a por $b es $answerValue."
            }
            6 -> {
                val a = int(2, 19); val b = int(2, 19)
                answerValue = a * b; text = "$a × $b"; explanation = "$a por $b es $answerValue."
            }
            7 -> {
                val a = int(2, 12); val b = int(2, 9); val c = int(2, 8)
                when (int(0, 4)) {
                    0 -> { answerValue = a + b * c; text = "$a + ($b × $c)"; explanation = "Primero $b × $c; después se suma $a." }
                    1 -> { answerValue = (a + b) * c; text = "($a + $b) × $c"; explanation = "Primero se resuelve el paréntesis y luego se multiplica por $c." }
                    2 -> { answerValue = a + b + c; text = "[$a + ($b + $c)]"; explanation = "Se resuelve primero el paréntesis interior." }
                    3 -> { answerValue = (a + b) * c - b; text = "{($a + $b) × $c} − $b"; explanation = "Paréntesis, multiplicación y finalmente resta." }
                    else -> { answerValue = a + b; text = "{${a * c} ÷ $c} + $b"; explanation = "Primero ${a * c} ÷ $c = $a; luego se suma $b." }
                }
                explanation += " Resultado: $answerValue."
            }
            8 -> {
                when (int(0, 4)) {
                    0 -> { val e = int(2, 10); val p = 1 shl e; val d = int(2, 9); answerValue = p + d; text = "2${if (e == 10) "¹⁰" else superscript[e]} + $d"; explanation = "La potencia vale $p; luego se suma $d." }
                    1 -> { val e = int(2, 7); val p = power(3, e); val d = int(2, 8); answerValue = p - d; text = "3${superscript[e]} − $d"; explanation = "La potencia vale $p; luego se resta $d." }
                    2 -> { val root = listOf(4, 9, 16, 25, 36, 49, 64, 81).random(random); val r = squareRoot(root); val e = int(2, 5); val p = 1 shl e; answerValue = r + p; text = "√$root + 2${superscript[e]}"; explanation = "√$root = $r y la potencia vale $p." }
                    3 -> { val e = int(2, 6); val p = 1 shl e; val divisor = listOf(2, 4).filter { p % it == 0 }.random(random); answerValue = p / divisor + 3; text = "[2${superscript[e]} ÷ $divisor] + √9"; explanation = "Se calcula la potencia, la división exacta y √9 = 3." }
                    else -> { val e = int(2, 5); val p = power(3, e); answerValue = p + 7; text = "{3${superscript[e]} + √49}"; explanation = "La potencia vale $p y √49 = 7." }
                }
                explanation += " Resultado: $answerValue."
            }
            9 -> {
                val coefficient = int(2, 9); val x = int(1, 12); val b = int(1, 15); val total = coefficient * x + b
                answerValue = x; text = "${coefficient}x + $b = $total\n¿Cuánto vale x?"; explanation = "Se resta $b y se divide entre $coefficient. x = $x."
            }
            10 -> {
                val factor = int(2, 9); val sum = int(3, 18); val total = factor * sum
                answerValue = sum; text = "${factor}a + ${factor}b = $total\n¿Cuánto vale a + b?"; explanation = "$factor(a + b) = $total; por tanto, a + b = $sum."
            }
            else -> return algebraQuestion(random)
        }

        return MathQuestion(text, answerValue.toString(), numericChoices(answerValue, random), explanation, level)
    }

    private fun numericChoices(answer: Int, random: Random): List<String> {
        val offsets = listOf(-10, 10, -2, 2, -1, 1, -5, 5, -9, 9).shuffled(random)
        val values = mutableListOf(answer)
        offsets.forEach { offset ->
            val candidate = answer + offset
            if (candidate >= 0 && candidate !in values && values.size < 3) values += candidate
        }
        var candidate = 0
        while (values.size < 3) { if (candidate !in values) values += candidate; candidate++ }
        return values.map(Int::toString).shuffled(random)
    }

    private fun algebraQuestion(random: Random): MathQuestion {
        val items = listOf(
            listOf("El doble de un número más 3", "2x + 3", "2(x + 3)", "x + 6"),
            listOf("La tercera parte de un número", "x ÷ 3", "3x", "x − 3"),
            listOf("Un número disminuido en 7", "x − 7", "7 − x", "7x"),
            listOf("El triple de la suma de un número y 4", "3(x + 4)", "3x + 4", "x + 12"),
            listOf("La mitad de un número aumentada en 5", "x ÷ 2 + 5", "x ÷ 7", "2x + 5"),
            listOf("La diferencia entre un número y su cuarta parte", "x − x ÷ 4", "x ÷ 4 − x", "4x − x"),
            listOf("El cuadrado de un número menos 6", "x² − 6", "(x − 6)²", "2x − 6"),
            listOf("La suma de dos números consecutivos", "x + (x + 1)", "x + 1", "2(x + 1)"),
            listOf("Cinco veces un número, disminuido en 2", "5x − 2", "5(x − 2)", "x − 10")
        )
        val item = items.random(random)
        return MathQuestion("Elige la expresión correcta:\n${item[0]}", item[1], item.drop(1).shuffled(random), "La expresión correcta es ${item[1]}.", 11)
    }

    private fun power(base: Int, exponent: Int): Int {
        var result = 1
        repeat(exponent) { result *= base }
        return result
    }

    private fun squareRoot(value: Int): Int = (1..9).first { it * it == value }
}
