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
 * Integration tests for AsgSerializer: parses COBOL fixtures with ProLeap,
 * serializes to JSON, and verifies the output matches the CobolASG contract.
 */
public class AsgSerializerTest {

    @BeforeClass
    public static void suppressLogging() {
        Logger.getLogger("io.proleap").setLevel(Level.OFF);
        Logger.getLogger("org.antlr").setLevel(Level.OFF);
    }

    // ── Hello World ──────────────────────────────────────────────────────

    @Test
    public void testHelloWorld_hasDataFields() throws Exception {
        JsonObject asg = parseFixture("hello_world.cbl");

        assertTrue("ASG must have data_fields", asg.has("data_fields"));
        JsonArray fields = asg.getAsJsonArray("data_fields");
        assertEquals("Should have 1 data field", 1, fields.size());

        JsonObject wsMsg = fields.get(0).getAsJsonObject();
        assertEquals("WS-MSG", wsMsg.get("name").getAsString());
        assertEquals(77, wsMsg.get("level").getAsInt());
        assertNotNull("Should have a PIC clause", wsMsg.get("pic"));
        assertEquals("DISPLAY", wsMsg.get("usage").getAsString());
    }

    @Test
    public void testHelloWorld_hasParagraphs() throws Exception {
        JsonObject asg = parseFixture("hello_world.cbl");

        assertTrue("ASG must have paragraphs", asg.has("paragraphs"));
        JsonArray paragraphs = asg.getAsJsonArray("paragraphs");
        assertTrue("Should have at least 1 paragraph", paragraphs.size() >= 1);

        JsonObject mainPara = findParagraph(paragraphs, "MAIN-PARA");
        assertNotNull("Should find MAIN-PARA", mainPara);

        JsonArray stmts = mainPara.getAsJsonArray("statements");
        assertNotNull("MAIN-PARA should have statements", stmts);
        assertTrue("Should have at least 2 statements", stmts.size() >= 2);

        assertStatementType(stmts, 0, "DISPLAY");
        assertLastStatementType(stmts, "STOP_RUN");
    }

    @Test
    public void testHelloWorld_displayOperands() throws Exception {
        JsonObject asg = parseFixture("hello_world.cbl");
        JsonObject mainPara = findParagraph(asg.getAsJsonArray("paragraphs"), "MAIN-PARA");
        JsonArray stmts = mainPara.getAsJsonArray("statements");
        JsonObject displayStmt = stmts.get(0).getAsJsonObject();

        assertEquals("DISPLAY", displayStmt.get("type").getAsString());
        assertTrue("DISPLAY should have operands", displayStmt.has("operands"));
        JsonArray operands = displayStmt.getAsJsonArray("operands");
        assertTrue("DISPLAY should reference WS-MSG",
                operands.get(0).getAsString().contains("WS-MSG"));
    }

    // ── Move Fields ──────────────────────────────────────────────────────

    @Test
    public void testMoveFields_hasDataFields() throws Exception {
        JsonObject asg = parseFixture("move_fields.cbl");

        JsonArray fields = asg.getAsJsonArray("data_fields");
        assertEquals("Should have 2 data fields", 2, fields.size());

        JsonObject wsSrc = fields.get(0).getAsJsonObject();
        assertEquals("WS-SRC", wsSrc.get("name").getAsString());
        assertEquals(77, wsSrc.get("level").getAsInt());

        JsonObject wsDst = fields.get(1).getAsJsonObject();
        assertEquals("WS-DST", wsDst.get("name").getAsString());
        assertEquals(77, wsDst.get("level").getAsInt());
    }

    @Test
    public void testMoveFields_moveStatement() throws Exception {
        JsonObject asg = parseFixture("move_fields.cbl");
        JsonObject mainPara = findParagraph(asg.getAsJsonArray("paragraphs"), "MAIN-PARA");
        JsonArray stmts = mainPara.getAsJsonArray("statements");

        assertStatementType(stmts, 0, "MOVE");

        JsonObject moveStmt = stmts.get(0).getAsJsonObject();
        assertTrue("MOVE should have operands", moveStmt.has("operands"));
        JsonArray operands = moveStmt.getAsJsonArray("operands");
        assertEquals("MOVE should have 2 operands (source + target)", 2, operands.size());
    }

    // ── Arithmetic ───────────────────────────────────────────────────────

    @Test
    public void testArithmetic_hasDataFields() throws Exception {
        JsonObject asg = parseFixture("arithmetic.cbl");

        JsonArray fields = asg.getAsJsonArray("data_fields");
        assertEquals("Should have 1 data field", 1, fields.size());

        JsonObject wsTotal = fields.get(0).getAsJsonObject();
        assertEquals("WS-TOTAL", wsTotal.get("name").getAsString());
        assertEquals(77, wsTotal.get("level").getAsInt());
    }

    @Test
    public void testArithmetic_computeStatements() throws Exception {
        JsonObject asg = parseFixture("arithmetic.cbl");
        JsonObject mainPara = findParagraph(asg.getAsJsonArray("paragraphs"), "MAIN-PARA");
        JsonArray stmts = mainPara.getAsJsonArray("statements");

        assertTrue("Should have at least 3 statements", stmts.size() >= 3);
        // ProLeap 4.0.0 bug: ADD/SUBTRACT fail to parse, using COMPUTE instead
        assertStatementType(stmts, 0, "COMPUTE");
        assertStatementType(stmts, 1, "COMPUTE");
        assertLastStatementType(stmts, "STOP_RUN");
    }

    @Test
    public void testArithmetic_computeOperands() throws Exception {
        JsonObject asg = parseFixture("arithmetic.cbl");
        JsonObject mainPara = findParagraph(asg.getAsJsonArray("paragraphs"), "MAIN-PARA");
        JsonArray stmts = mainPara.getAsJsonArray("statements");
        JsonObject computeStmt = stmts.get(0).getAsJsonObject();

        assertTrue("COMPUTE should have operands", computeStmt.has("operands"));
        JsonArray operands = computeStmt.getAsJsonArray("operands");
        assertTrue("COMPUTE should have at least 1 operand", operands.size() >= 1);
    }

    // ── DataFieldSerializer unit tests ───────────────────────────────────

    @Test
    public void testPicByteLength_display() {
        assertEquals(5, DataFieldSerializer.computePicByteLength("9(5)", "DISPLAY"));
        assertEquals(3, DataFieldSerializer.computePicByteLength("X(3)", "DISPLAY"));
        assertEquals(11, DataFieldSerializer.computePicByteLength("X(11)", "DISPLAY"));
        assertEquals(7, DataFieldSerializer.computePicByteLength("S9(5)V99", "DISPLAY"));
    }

    @Test
    public void testPicByteLength_comp3() {
        // COMP-3: (total_digits // 2) + 1 (matches Python CobolTypeDescriptor.byte_length)
        assertEquals(3, DataFieldSerializer.computePicByteLength("9(5)", "COMP-3"));
        assertEquals(4, DataFieldSerializer.computePicByteLength("S9(5)V99", "COMP-3"));
    }

    @Test
    public void testPicByteLength_comp() {
        // COMP: ≤4 digits → 2, ≤9 → 4, ≤18 → 8
        assertEquals(2, DataFieldSerializer.computePicByteLength("9(3)", "COMP"));
        assertEquals(4, DataFieldSerializer.computePicByteLength("9(5)", "COMP"));
        assertEquals(8, DataFieldSerializer.computePicByteLength("9(15)", "COMP"));
    }

    @Test
    public void testCountStoragePositions() {
        assertEquals(5, DataFieldSerializer.countStoragePositions("9(5)"));
        assertEquals(3, DataFieldSerializer.countStoragePositions("X(3)"));
        assertEquals(7, DataFieldSerializer.countStoragePositions("S9(5)V99"));
        assertEquals(11, DataFieldSerializer.countStoragePositions("X(11)"));
        assertEquals(3, DataFieldSerializer.countStoragePositions("999"));
        assertEquals(1, DataFieldSerializer.countStoragePositions("9"));
    }

    // ── Helpers ──────────────────────────────────────────────────────────

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
        // Check inside sections too
        return null;
    }

    private void assertStatementType(JsonArray stmts, int index, String expectedType) {
        JsonObject stmt = stmts.get(index).getAsJsonObject();
        assertEquals("Statement " + index + " type", expectedType, stmt.get("type").getAsString());
    }

    private void assertLastStatementType(JsonArray stmts, String expectedType) {
        JsonObject lastStmt = stmts.get(stmts.size() - 1).getAsJsonObject();
        assertEquals("Last statement type", expectedType, lastStmt.get("type").getAsString());
    }
}
