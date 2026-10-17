package org.reddragon.bridge;

import java.util.regex.Pattern;

/**
 * The canonical text of a numeric literal: its decimal point written as a period.
 *
 * <p>DECIMAL-POINT IS COMMA "exchanges the functions of the period and the comma
 * in PICTURE character-strings and in numeric literals" (IBM Enterprise COBOL
 * LR, SPECIAL-NAMES paragraph). The lexer's NUMERICLITERAL accepts either
 * character, so a program under the clause writes {@code 1234,56} for the value
 * the rest of the pipeline reads as {@code 1234.56}. The clause is per program,
 * and one bridge run serializes one program, so {@link AsgSerializer} sets it
 * before anything is serialized.
 */
final class NumericLiteralText {

    private static final Pattern COMMA_POINT_LITERAL =
            Pattern.compile("[+-]?[0-9]*,[0-9]+([eE][+-]?[0-9]+)?");

    private static boolean decimalPointIsComma = false;

    private NumericLiteralText() {
    }

    static void useDecimalPointIsComma(boolean comma) {
        decimalPointIsComma = comma;
    }

    static String canonical(String text) {
        if (decimalPointIsComma && COMMA_POINT_LITERAL.matcher(text).matches()) {
            return text.replace(',', '.');
        }
        return text;
    }
}
