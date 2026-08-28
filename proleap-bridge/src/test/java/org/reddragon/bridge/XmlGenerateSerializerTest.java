package org.reddragon.bridge;

import com.google.gson.JsonArray;
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
 * XML GENERATE serialization. Without a serializer of its own the statement
 * falls through to serializeUnknown, which emits the type and nothing else --
 * and the Python side then has a statement whose operands are all gone.
 */
public class XmlGenerateSerializerTest {

    @BeforeClass
    public static void suppressLogging() {
        Logger.getLogger("io.proleap").setLevel(Level.OFF);
        Logger.getLogger("org.antlr").setLevel(Level.OFF);
    }

    @Test
    public void testXmlGenerate_documentAndSourceRecord() throws Exception {
        JsonObject stmt = statement(0);

        assertEquals("XML_GENERATE", stmt.get("type").getAsString());
        assertEquals("WRITE-REC", stmt.get("xml_document").getAsString());
        assertEquals("SOME-RECORD", stmt.get("from_record").getAsString());
    }

    @Test
    public void testXmlGenerate_bareFormHasNoCountOrPhrases() throws Exception {
        JsonObject stmt = statement(0);

        assertFalse("bare form has no COUNT IN", stmt.has("count_in"));
        assertEquals(0, stmt.getAsJsonArray("on_exception").size());
        assertEquals(0, stmt.getAsJsonArray("not_on_exception").size());
    }

    @Test
    public void testXmlGenerate_countInAndExceptionPhrases() throws Exception {
        JsonObject stmt = statement(1);

        assertEquals("WS-XML-LEN", stmt.get("count_in").getAsString());

        JsonArray onException = stmt.getAsJsonArray("on_exception");
        assertEquals(1, onException.size());
        assertEquals("MOVE", onException.get(0).getAsJsonObject().get("type").getAsString());

        JsonArray notOnException = stmt.getAsJsonArray("not_on_exception");
        assertEquals(1, notOnException.size());
        assertEquals("MOVE", notOnException.get(0).getAsJsonObject().get("type").getAsString());
    }

    // ── Helpers ──────────────────────────────────────────────────────────

    private JsonObject statement(int index) throws Exception {
        URL resource = getClass().getClassLoader().getResource("fixtures/xml_generate.cbl");
        assertNotNull("Fixture not found", resource);

        Program program = new CobolParserRunnerImpl()
                .analyzeFile(new File(resource.toURI()), CobolSourceFormatEnum.FIXED);
        JsonObject asg = AsgSerializer.serialize(program);

        JsonArray statements = asg.getAsJsonArray("statements");
        assertNotNull("ASG must have division-level statements", statements);
        return statements.get(index).getAsJsonObject();
    }
}
