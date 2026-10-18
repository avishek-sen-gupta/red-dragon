package org.reddragon.bridge;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import io.proleap.cobol.asg.metamodel.Program;
import io.proleap.cobol.asg.runner.impl.CobolParserRunnerImpl;
import io.proleap.cobol.preprocessor.CobolPreprocessor.CobolSourceFormatEnum;
import org.junit.BeforeClass;
import org.junit.Test;

import java.io.File;
import java.net.URL;
import java.util.logging.Level;
import java.util.logging.Logger;

import static org.junit.Assert.*;

/**
 * CANCEL's operands: Cobol.g4 is {@code cancelCall : libraryName (BYTITLE|BYFUNCTION) |
 * identifier | literal}. Each operand is serialized as CALL's callee is: a literal as
 * {@code program}, an identifier as a structured {@code program_ref}, so the frontend can
 * read the identifier's contents at run time. (red-dragon-pvcb)
 */
public class CancelTargetSerializerTest {

    @BeforeClass
    public static void suppressLogging() {
        Logger.getLogger("io.proleap").setLevel(Level.OFF);
        Logger.getLogger("org.antlr").setLevel(Level.OFF);
    }

    @Test
    public void eachOperandIsALiteralNameOrAStructuredReference() throws Exception {
        JsonArray programs = cancel().getAsJsonArray("programs");
        assertEquals(3, programs.size());

        JsonObject literal = programs.get(0).getAsJsonObject();
        assertEquals("SUBC", literal.get("program").getAsString());
        assertFalse(literal.has("program_ref"));

        JsonObject sliced = programs.get(1).getAsJsonObject();
        assertFalse(sliced.has("program"));
        JsonObject slicedRef = sliced.getAsJsonObject("program_ref");
        assertEquals("WS-PROG", slicedRef.get("name").getAsString());
        assertEquals("1", slicedRef.getAsJsonObject("ref_mod_start").get("value").getAsString());
        assertEquals("8", slicedRef.getAsJsonObject("ref_mod_length").get("value").getAsString());

        JsonObject qualifiedRef = programs.get(2).getAsJsonObject().getAsJsonObject("program_ref");
        assertEquals("WS-INNER", qualifiedRef.get("name").getAsString());
        assertEquals("WS-GRP", qualifiedRef.getAsJsonArray("qualifiers").get(0).getAsString());
    }

    private JsonObject cancel() throws Exception {
        URL resource = getClass().getClassLoader().getResource("fixtures/cancel_target.cbl");
        assertNotNull("Fixture not found", resource);
        Program program = new CobolParserRunnerImpl()
                .analyzeFile(new File(resource.toURI()), CobolSourceFormatEnum.FIXED);
        JsonObject asg = AsgSerializer.serialize(program).getAsJsonArray("programs").get(0).getAsJsonObject();
        for (JsonElement p : asg.getAsJsonArray("paragraphs")) {
            for (JsonElement s : p.getAsJsonObject().getAsJsonArray("statements")) {
                if ("CANCEL".equals(s.getAsJsonObject().get("type").getAsString())) {
                    return s.getAsJsonObject();
                }
            }
        }
        throw new AssertionError("CANCEL not serialized");
    }
}
