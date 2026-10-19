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
 * CLOSE's per-file phrases (Cobol.g4 closeReelUnitStatement and closeRelativeStatement)
 * reach the JSON as written: which files name REEL or UNIT, FOR REMOVAL, NO REWIND and
 * LOCK. (red-dragon-sl30.94)
 */
public class ClosePhraseSerializerTest {

    @BeforeClass
    public static void suppressLogging() {
        Logger.getLogger("io.proleap").setLevel(Level.OFF);
        Logger.getLogger("org.antlr").setLevel(Level.OFF);
    }

    @Test
    public void eachFilesPhraseIsListedByFile() throws Exception {
        JsonObject close = close();
        assertEquals(List.of("F1", "F2", "F3", "F4", "F5"), names(close, "files"));
        assertEquals(List.of("F1", "F2", "F3"), names(close, "reel_unit"));
        assertEquals(List.of("F2"), names(close, "for_removal"));
        assertEquals(List.of("F3", "F4"), names(close, "no_rewind"));
        assertEquals(List.of("F5"), names(close, "with_lock"));
    }

    private List<String> names(JsonObject close, String key) {
        List<String> out = new ArrayList<>();
        for (JsonElement e : close.getAsJsonArray(key)) {
            out.add(e.getAsString());
        }
        return out;
    }

    private JsonObject close() throws Exception {
        URL resource = getClass().getClassLoader().getResource("fixtures/close_phrases.cbl");
        assertNotNull("Fixture not found", resource);
        Program program = new CobolParserRunnerImpl()
                .analyzeFile(new File(resource.toURI()), CobolSourceFormatEnum.FIXED);
        JsonObject asg = AsgSerializer.serialize(program).getAsJsonArray("programs").get(0).getAsJsonObject();
        for (JsonElement p : asg.getAsJsonArray("paragraphs")) {
            for (JsonElement s : p.getAsJsonObject().getAsJsonArray("statements")) {
                if ("CLOSE".equals(s.getAsJsonObject().get("type").getAsString())) {
                    return s.getAsJsonObject();
                }
            }
        }
        throw new AssertionError("CLOSE not serialized");
    }
}
