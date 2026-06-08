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
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Level;
import java.util.logging.Logger;

import static org.junit.Assert.*;

/**
 * Tests for reference modification serialization in MOVE operands.
 */
public class RefModSerializerTest {

    @BeforeClass
    public static void suppressLogging() {
        Logger.getLogger("io.proleap").setLevel(Level.OFF);
        Logger.getLogger("org.antlr").setLevel(Level.OFF);
    }

    @Test
    public void testRefMod_literalStartLength() throws Exception {
        JsonObject src = getMoveSourceOperand(0);
        assertEquals("WS-FIELD", src.get("name").getAsString());
        assertTrue("must have ref_mod_start", src.has("ref_mod_start"));
        assertTrue("must have ref_mod_length", src.has("ref_mod_length"));
        JsonObject start = src.getAsJsonObject("ref_mod_start");
        assertEquals("lit", start.get("kind").getAsString());
        assertEquals("2", start.get("value").getAsString());
        JsonObject len = src.getAsJsonObject("ref_mod_length");
        assertEquals("lit", len.get("kind").getAsString());
        assertEquals("3", len.get("value").getAsString());
    }

    @Test
    public void testRefMod_datanameStartLength() throws Exception {
        JsonObject src = getMoveSourceOperand(1);
        assertEquals("WS-FIELD", src.get("name").getAsString());
        JsonObject start = src.getAsJsonObject("ref_mod_start");
        assertEquals("ref", start.get("kind").getAsString());
        assertEquals("WS-A", start.get("name").getAsString());
        JsonObject len = src.getAsJsonObject("ref_mod_length");
        assertEquals("ref", len.get("kind").getAsString());
        assertEquals("WS-B", len.get("name").getAsString());
    }

    @Test
    public void testRefMod_addSubtractExpr() throws Exception {
        JsonObject src = getMoveSourceOperand(2);
        // start = WS-A + 1
        JsonObject start = src.getAsJsonObject("ref_mod_start");
        assertEquals("binop", start.get("kind").getAsString());
        assertEquals("+", start.get("op").getAsString());
        assertEquals("ref", start.getAsJsonObject("left").get("kind").getAsString());
        assertEquals("WS-A", start.getAsJsonObject("left").get("name").getAsString());
        assertEquals("lit", start.getAsJsonObject("right").get("kind").getAsString());
        assertEquals("1", start.getAsJsonObject("right").get("value").getAsString());
        // length = WS-B - 1
        JsonObject len = src.getAsJsonObject("ref_mod_length");
        assertEquals("binop", len.get("kind").getAsString());
        assertEquals("-", len.get("op").getAsString());
        assertEquals("WS-B", len.getAsJsonObject("left").get("name").getAsString());
        assertEquals("1", len.getAsJsonObject("right").get("value").getAsString());
    }

    @Test
    public void testRefMod_multiplyExpr() throws Exception {
        JsonObject src = getMoveSourceOperand(3);
        // start = WS-A * WS-B
        JsonObject start = src.getAsJsonObject("ref_mod_start");
        assertEquals("binop", start.get("kind").getAsString());
        assertEquals("*", start.get("op").getAsString());
        assertEquals("WS-A", start.getAsJsonObject("left").get("name").getAsString());
        assertEquals("WS-B", start.getAsJsonObject("right").get("name").getAsString());
    }

    @Test
    public void testRefMod_parenthesisedExpr() throws Exception {
        JsonObject src = getMoveSourceOperand(4);
        // start = (WS-A + 1) * 2
        JsonObject start = src.getAsJsonObject("ref_mod_start");
        assertEquals("binop", start.get("kind").getAsString());
        assertEquals("*", start.get("op").getAsString());
        JsonObject left = start.getAsJsonObject("left");
        assertEquals("binop", left.get("kind").getAsString());
        assertEquals("+", left.get("op").getAsString());
        assertEquals("lit", start.getAsJsonObject("right").get("kind").getAsString());
        assertEquals("2", start.getAsJsonObject("right").get("value").getAsString());
    }

    @Test
    public void testRefMod_omittedLength() throws Exception {
        JsonObject src = getMoveSourceOperand(5);
        assertEquals("WS-FIELD", src.get("name").getAsString());
        assertTrue("must have ref_mod_start", src.has("ref_mod_start"));
        assertFalse("ref_mod_length key must be absent when omitted", src.has("ref_mod_length"));
    }

    @Test
    public void testRefMod_deeplyNested() throws Exception {
        JsonObject src = getMoveSourceOperand(6);
        // start = (WS-A + WS-B) * (WS-C - WS-A)
        JsonObject start = src.getAsJsonObject("ref_mod_start");
        assertEquals("binop", start.get("kind").getAsString());
        assertEquals("*", start.get("op").getAsString());
        JsonObject left = start.getAsJsonObject("left");
        assertEquals("binop", left.get("kind").getAsString());
        assertEquals("+", left.get("op").getAsString());
        JsonObject right = start.getAsJsonObject("right");
        assertEquals("binop", right.get("kind").getAsString());
        assertEquals("-", right.get("op").getAsString());
    }

    @Test
    public void testRefMod_targetOperand() throws Exception {
        // All MOVE target operands (index 1) should be objects with name "WS-OUT", no ref_mod keys
        JsonObject asg = parseFixture("ref_mod.cbl");
        List<JsonObject> moves = getMoveStatements(asg);
        for (int i = 0; i < 7; i++) {
            JsonObject tgt = moves.get(i).getAsJsonArray("operands").get(1).getAsJsonObject();
            assertEquals("WS-OUT", tgt.get("name").getAsString());
            assertFalse("target should have no ref_mod_start", tgt.has("ref_mod_start"));
            assertFalse("target should have no ref_mod_length", tgt.has("ref_mod_length"));
        }
    }

    @Test
    public void testRefMod_plainMoveUnchanged() throws Exception {
        // MOVE #8 is MOVE WS-A TO WS-OUT — no ref mod
        JsonObject src = getMoveSourceOperand(7);
        assertEquals("WS-A", src.get("name").getAsString());
        assertFalse("plain MOVE source has no ref_mod_start", src.has("ref_mod_start"));
        assertFalse("plain MOVE source has no ref_mod_length", src.has("ref_mod_length"));
    }

    @Test
    public void testRefMod_lengthOfInTargetExpr() throws Exception {
        // MOVE #9 is MOVE WS-FIELD TO WS-OUT(LENGTH OF WS-A + 1:LENGTH OF WS-B).
        // LENGTH OF must serialize as a structured length_of node — NOT a bogus
        // ref node named "LENGTHOFWS-A" (which the frontend resolves to 0,
        // collapsing the ref-mod offset and shifting bytes). (red-dragon-oq2c)
        JsonObject asg = parseFixture("ref_mod.cbl");
        List<JsonObject> moves = getMoveStatements(asg);
        JsonObject tgt = moves.get(8).getAsJsonArray("operands").get(1).getAsJsonObject();
        assertEquals("WS-OUT", tgt.get("name").getAsString());

        // start = LENGTH OF WS-A + 1
        JsonObject start = tgt.getAsJsonObject("ref_mod_start");
        assertEquals("binop", start.get("kind").getAsString());
        assertEquals("+", start.get("op").getAsString());
        JsonObject startLeft = start.getAsJsonObject("left");
        assertEquals("length_of", startLeft.get("kind").getAsString());
        assertEquals("WS-A", startLeft.get("name").getAsString());
        JsonObject startRight = start.getAsJsonObject("right");
        assertEquals("lit", startRight.get("kind").getAsString());
        assertEquals("1", startRight.get("value").getAsString());

        // length = LENGTH OF WS-B
        JsonObject len = tgt.getAsJsonObject("ref_mod_length");
        assertEquals("length_of", len.get("kind").getAsString());
        assertEquals("WS-B", len.get("name").getAsString());
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private JsonObject getMoveSourceOperand(int moveIndex) throws Exception {
        JsonObject asg = parseFixture("ref_mod.cbl");
        List<JsonObject> moves = getMoveStatements(asg);
        return moves.get(moveIndex).getAsJsonArray("operands").get(0).getAsJsonObject();
    }

    private List<JsonObject> getMoveStatements(JsonObject asg) {
        JsonObject para = findParagraph(asg.getAsJsonArray("paragraphs"), "MAIN-PARA");
        assertNotNull("MAIN-PARA must exist", para);
        JsonArray stmts = para.getAsJsonArray("statements");
        List<JsonObject> moves = new ArrayList<>();
        for (JsonElement e : stmts) {
            JsonObject s = e.getAsJsonObject();
            if ("MOVE".equals(s.get("type").getAsString())) {
                moves.add(s);
            }
        }
        return moves;
    }

    private JsonObject parseFixture(String filename) throws Exception {
        URL resource = getClass().getClassLoader().getResource("fixtures/" + filename);
        assertNotNull("Fixture not found: " + filename, resource);
        File file = new File(resource.toURI());
        Program program = new CobolParserRunnerImpl()
                .analyzeFile(file, CobolSourceFormatEnum.FIXED);
        return AsgSerializer.serialize(program);
    }

    private JsonObject findParagraph(JsonArray paragraphs, String name) {
        for (JsonElement elem : paragraphs) {
            JsonObject para = elem.getAsJsonObject();
            if (name.equalsIgnoreCase(para.get("name").getAsString())) {
                return para;
            }
        }
        return null;
    }
}
