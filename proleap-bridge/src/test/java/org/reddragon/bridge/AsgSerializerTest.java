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
                operands.get(0).getAsJsonObject().get("name").getAsString().contains("WS-MSG"));
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
        
        // New validation: MOVE operands are now objects with "name" property
        JsonObject sourceOp = operands.get(0).getAsJsonObject();
        assertEquals("Source operand should have name property", "WS-SRC", sourceOp.get("name").getAsString());
        
        JsonObject targetOp = operands.get(1).getAsJsonObject();
        assertEquals("Target operand should have name property", "WS-DST", targetOp.get("name").getAsString());
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
    public void testArithmetic_addAndSubtract() throws Exception {
        JsonObject asg = parseFixture("arithmetic.cbl");
        JsonObject mainPara = findParagraph(asg.getAsJsonArray("paragraphs"), "MAIN-PARA");
        JsonArray stmts = mainPara.getAsJsonArray("statements");

        assertTrue("Should have at least 3 statements", stmts.size() >= 3);
        assertStatementType(stmts, 0, "ADD");
        assertStatementType(stmts, 1, "SUBTRACT");
        assertLastStatementType(stmts, "STOP_RUN");
    }

    @Test
    public void testArithmetic_addOperands() throws Exception {
        JsonObject asg = parseFixture("arithmetic.cbl");
        JsonObject mainPara = findParagraph(asg.getAsJsonArray("paragraphs"), "MAIN-PARA");
        JsonArray stmts = mainPara.getAsJsonArray("statements");
        JsonObject addStmt = stmts.get(0).getAsJsonObject();

        assertTrue("ADD should have operands", addStmt.has("operands"));
        JsonArray operands = addStmt.getAsJsonArray("operands");
        assertEquals("ADD should have 2 operands (from + to)", 2, operands.size());
    }

    // ── Bare Statements (division-level) ───────────────────────────────

    @Test
    public void testBareStatements_hasDivisionStatements() throws Exception {
        JsonObject asg = parseFixture("bare_statements.cbl");

        assertTrue("ASG must have statements", asg.has("statements"));
        JsonArray stmts = asg.getAsJsonArray("statements");
        assertEquals("Should have 3 bare statements", 3, stmts.size());

        assertStatementType(stmts, 0, "COMPUTE");
        assertStatementType(stmts, 1, "DISPLAY");
        assertStatementType(stmts, 2, "STOP_RUN");
    }

    @Test
    public void testBareStatements_noParagraphs() throws Exception {
        JsonObject asg = parseFixture("bare_statements.cbl");

        assertFalse("ASG should not have paragraphs", asg.has("paragraphs"));
    }

    // ── Bare Statements (section-level) ──────────────────────────────────

    @Test
    public void testSectionBareStatements_hasSectionStatements() throws Exception {
        JsonObject asg = parseFixture("section_bare_statements.cbl");

        assertTrue("ASG must have sections", asg.has("sections"));
        JsonArray sections = asg.getAsJsonArray("sections");
        assertTrue("Should have at least 1 section", sections.size() >= 1);

        JsonObject mainSection = sections.get(0).getAsJsonObject();
        assertEquals("MAIN-SECTION", mainSection.get("name").getAsString());

        assertTrue("Section must have statements", mainSection.has("statements"));
        JsonArray stmts = mainSection.getAsJsonArray("statements");
        assertEquals("Should have 3 section-level bare statements", 3, stmts.size());

        assertStatementType(stmts, 0, "COMPUTE");
        assertStatementType(stmts, 1, "DISPLAY");
        assertStatementType(stmts, 2, "STOP_RUN");
    }

    @Test
    public void testSectionBareStatements_noParagraphs() throws Exception {
        JsonObject asg = parseFixture("section_bare_statements.cbl");

        JsonArray sections = asg.getAsJsonArray("sections");
        JsonObject mainSection = sections.get(0).getAsJsonObject();

        assertFalse("Section should not have paragraphs", mainSection.has("paragraphs"));
    }

    // ── Linkage Section ──────────────────────────────────────────────────

    @Test
    public void testLinkageSection_hasLinkageFields() throws Exception {
        JsonObject asg = parseFixture("linkage_section.cbl");

        assertTrue("ASG must have linkage_fields", asg.has("linkage_fields"));
        JsonArray fields = asg.getAsJsonArray("linkage_fields");
        assertEquals("Should have 2 linkage fields", 2, fields.size());

        JsonObject lsInput = fields.get(0).getAsJsonObject();
        assertEquals("LS-INPUT", lsInput.get("name").getAsString());

        JsonObject lsOutput = fields.get(1).getAsJsonObject();
        assertEquals("LS-OUTPUT", lsOutput.get("name").getAsString());
    }

    @Test
    public void testLinkageSection_noWorkingStorage() throws Exception {
        JsonObject asg = parseFixture("linkage_section.cbl");

        assertFalse("ASG must not have data_fields when there is no WORKING-STORAGE", asg.has("data_fields"));
    }

    @Test
    public void testLinkageSection_withWorkingStorage() throws Exception {
        JsonObject asg = parseFixture("linkage_with_working_storage.cbl");

        assertTrue("ASG must have data_fields", asg.has("data_fields"));
        assertTrue("ASG must have linkage_fields", asg.has("linkage_fields"));

        JsonArray wsFields = asg.getAsJsonArray("data_fields");
        assertEquals("Should have 1 working-storage field", 1, wsFields.size());
        assertEquals("WS-RESULT", wsFields.get(0).getAsJsonObject().get("name").getAsString());

        JsonArray lsFields = asg.getAsJsonArray("linkage_fields");
        assertEquals("Should have 1 linkage field", 1, lsFields.size());
        assertEquals("LS-INPUT", lsFields.get(0).getAsJsonObject().get("name").getAsString());
    }

    // ── Local Storage Section ─────────────────────────────────────────────

    @Test
    public void testLocalStorageSection_hasLocalStorageFields() throws Exception {
        JsonObject asg = parseFixture("local_storage_section.cbl");

        assertTrue("ASG must have local_storage_fields", asg.has("local_storage_fields"));
        JsonArray fields = asg.getAsJsonArray("local_storage_fields");
        assertEquals("Should have 1 local-storage field", 1, fields.size());

        JsonObject lsCount = fields.get(0).getAsJsonObject();
        assertEquals("LS-COUNT", lsCount.get("name").getAsString());
    }

    @Test
    public void testLocalStorageSection_noLinkageFields() throws Exception {
        JsonObject asg = parseFixture("local_storage_section.cbl");

        assertFalse("ASG must not have linkage_fields", asg.has("linkage_fields"));
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

    @Test
    public void testNumericEditedStoragePositions() {
        // Numeric-edited pictures: every position (sign, digits, '.', ',') is
        // a stored byte, so size by full character width.
        assertEquals(12, DataFieldSerializer.countStoragePositions("+99999999.99"));
        assertEquals(15, DataFieldSerializer.countStoragePositions("+ZZZ,ZZZ,ZZZ.99"));
        assertEquals(13, DataFieldSerializer.countStoragePositions("Z(9).99-"));
        assertEquals(15, DataFieldSerializer.countStoragePositions("-ZZZ,ZZZ,ZZZ.ZZ"));
        // Plain numerics/alphanumerics remain digit/char counts. There is no
        // longer an isNumericEdited classification to assert against — one
        // uniform rule sizes every picture (red-dragon-ilb6).
        assertEquals(7, DataFieldSerializer.countStoragePositions("S9(5)V99"));
        assertEquals(8, DataFieldSerializer.countStoragePositions("X(8)"));
    }

    /**
     * B / 0 / slash insertion positions each occupy a byte. red-dragon-r9s9 taught
     * the Python side this (commits 30dcb974 -> 39b1d248) but was never mirrored
     * here, so the bridge under-allocated and every later field in the record slid
     * backwards (red-dragon-ilb6).
     */
    @Test
    public void testInsertionPositionsOccupyBytes() {
        assertEquals(8, DataFieldSerializer.countStoragePositions("9(5)BB9"));
        assertEquals(8, DataFieldSerializer.countStoragePositions("99/99/99"));
        assertEquals(5, DataFieldSerializer.countStoragePositions("9(3)09"));
    }

    /**
     * A picture with no 9/Z at all (all floating currency) previously failed the
     * numeric-edited gate, fell through to the token regex, matched nothing, and
     * was allocated ZERO bytes — its successor was laid on top of it.
     */
    @Test
    public void testAllFloatingPictureIsSizedByCharacterWidth() {
        assertEquals(7, DataFieldSerializer.countStoragePositions("$$$$.$$"));
        assertEquals(7, DataFieldSerializer.countStoragePositions("$(4).99"));
        assertEquals(7, DataFieldSerializer.countStoragePositions("++++.99"));
    }

    /** S, V and P are the only PIC symbols that occupy no storage. */
    @Test
    public void testScalingAndImpliedPointPositionsAreNotStored() {
        assertEquals(1, DataFieldSerializer.countStoragePositions("PPP9"));
        assertEquals(1, DataFieldSerializer.countStoragePositions("9PPP"));
        assertEquals(7, DataFieldSerializer.countStoragePositions("S9(5)V99"));
        assertEquals(12, DataFieldSerializer.countStoragePositions("S9(10)V99"));
    }

    /** Currency and check-protection positions are stored bytes like any other. */
    @Test
    public void testCurrencyAndCheckProtectionPositionsAreStored() {
        assertEquals(9, DataFieldSerializer.countStoragePositions("$$,$$$.99"));
        assertEquals(9, DataFieldSerializer.countStoragePositions("**,***.99"));
        assertEquals(8, DataFieldSerializer.countStoragePositions("*(5).99"));
        assertEquals(11, DataFieldSerializer.countStoragePositions("$ZZZ,ZZZ.99"));
        assertEquals(8, DataFieldSerializer.countStoragePositions("ZZZ.99CR"));
        assertEquals(8, DataFieldSerializer.countStoragePositions("ZZ9.99DB"));
    }

    /**
     * The assertion that would actually have caught red-dragon-ilb6: consecutive
     * fields must be laid out contiguously and must not overlap. Unit-testing the
     * width alone never exercised the offset accumulator that consumes it.
     */
    @Test
    public void testEditedFieldsGetContiguousNonOverlappingOffsets() throws Exception {
        JsonObject asg = parseFixture("EditWidths.cbl");
        JsonArray children = asg.getAsJsonArray("data_fields").get(0)
                .getAsJsonObject().getAsJsonArray("children");

        // Each edited field is followed by a PIC X(4) sentinel, so the gap between
        // one field's offset and the next is exactly the edited field's width.
        int[] expectedWidths = {8, 4, 8, 4, 5, 4, 7, 4};
        int expectedOffset = 0;
        for (int i = 0; i < expectedWidths.length; i++) {
            JsonObject fld = children.get(i).getAsJsonObject();
            assertEquals(
                    "offset of " + fld.get("name").getAsString()
                            + " (pic " + fld.get("pic").getAsString() + ")",
                    expectedOffset,
                    fld.get("offset").getAsInt());
            expectedOffset += expectedWidths[i];
        }
    }

    /**
     * SPECIAL-NAMES CURRENCY SIGN IS must reach the JSON contract. ProLeap's
     * CurrencySignClause exposes getCurrencyLiteral() / getPictureSymbolLiteral(),
     * but the bridge never read the SPECIAL-NAMES paragraph at all before this
     * (red-dragon-3o5f).
     */
    @Test
    public void testCurrencySignIsSerialized() throws Exception {
        JsonObject asg = parseFixture("CurrencySign.cbl");
        assertTrue("special_names missing from the ASG", asg.has("special_names"));
        JsonObject sn = asg.getAsJsonObject("special_names");
        assertEquals("W", sn.get("currency_sign").getAsString());
    }

    /**
     * A program with no SPECIAL-NAMES paragraph must not grow a spurious
     * currency_sign — Python defaults to '$' when the key is absent.
     */
    @Test
    public void testNoSpecialNamesEmitsNoCurrencySign() throws Exception {
        JsonObject asg = parseFixture("hello_world.cbl");
        if (asg.has("special_names")) {
            JsonObject sn = asg.getAsJsonObject("special_names");
            assertFalse("currency_sign emitted for a program without SPECIAL-NAMES",
                    sn.has("currency_sign"));
        }
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
