package org.reddragon.bridge;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
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
 * An FD's LINAGE clause, a WRITE's ADVANCING and END-OF-PAGE phrases, and the file-name
 * qualifying LINAGE-COUNTER reach the JSON as written (red-dragon-sl30.75).
 */
public class LinageSerializerTest {

    @BeforeClass
    public static void suppressLogging() {
        Logger.getLogger("io.proleap").setLevel(Level.OFF);
        Logger.getLogger("org.antlr").setLevel(Level.OFF);
    }

    @Test
    public void linageClauseWriteAdvancingAndQualifiedCounterAreSerialised() throws Exception {
        JsonObject asg = program();
        JsonArray fds = asg.getAsJsonArray("file_descriptions");
        assertEquals(
                JsonParser.parseString(
                        "{\"lines\":{\"kind\":\"lit\",\"value\":\"5\"},"
                                + "\"footing\":{\"kind\":\"lit\",\"value\":\"4\"},"
                                + "\"top\":{\"kind\":\"lit\",\"value\":\"1\"},"
                                + "\"bottom\":{\"kind\":\"lit\",\"value\":\"2\"}}"),
                fds.get(0).getAsJsonObject().get("linage"));
        assertEquals(
                JsonParser.parseString("{\"lines\":{\"kind\":\"ref\",\"name\":\"QL\"}}"),
                fds.get(1).getAsJsonObject().get("linage"));
        List<JsonObject> statements = statements(asg);
        JsonObject before = statements.get(0);
        assertEquals(
                JsonParser.parseString(
                        "{\"position\":\"BEFORE\",\"kind\":\"LINES\","
                                + "\"lines\":{\"kind\":\"ref\",\"name\":\"N\"}}"),
                before.get("advancing"));
        assertEquals("DISPLAY", first(before, "at_end_of_page").get("type").getAsString());
        assertEquals("DISPLAY", first(before, "not_at_end_of_page").get("type").getAsString());
        JsonObject page = statements.get(1);
        assertEquals(
                JsonParser.parseString("{\"position\":\"AFTER\",\"kind\":\"PAGE\"}"),
                page.get("advancing"));
        assertEquals(0, page.getAsJsonArray("at_end_of_page").size());
        JsonObject counter = statements.get(2).getAsJsonArray("operands").get(0).getAsJsonObject();
        assertEquals(
                JsonParser.parseString(
                        "{\"kind\":\"ref\",\"name\":\"LINAGE-COUNTER\",\"qualifiers\":[\"P\"]}"),
                counter);
    }

    private JsonObject first(JsonObject statement, String key) {
        return statement.getAsJsonArray(key).get(0).getAsJsonObject();
    }

    private List<JsonObject> statements(JsonObject asg) {
        List<JsonObject> out = new ArrayList<>();
        for (JsonElement p : asg.getAsJsonArray("paragraphs")) {
            for (JsonElement s : p.getAsJsonObject().getAsJsonArray("statements")) {
                out.add(s.getAsJsonObject());
            }
        }
        return out;
    }

    private JsonObject program() throws Exception {
        URL resource = getClass().getClassLoader().getResource("fixtures/linage.cbl");
        assertNotNull("Fixture not found", resource);
        Program program = new CobolParserRunnerImpl()
                .analyzeFile(new File(resource.toURI()), CobolSourceFormatEnum.FIXED);
        return AsgSerializer.serialize(program).getAsJsonArray("programs").get(0).getAsJsonObject();
    }
}
