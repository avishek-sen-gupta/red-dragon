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

/** Each entry's own SIGN clause is serialised as written; none is inherited here. */
public class GroupSignSerializerTest {

    @BeforeClass
    public static void suppressLogging() {
        Logger.getLogger("io.proleap").setLevel(Level.OFF);
        Logger.getLogger("org.antlr").setLevel(Level.OFF);
    }

    @Test
    public void eachEntryCarriesOnlyItsOwnSignClause() throws Exception {
        JsonObject asg = serializeFixture("group_sign.cbl");

        assertEquals("{\"position\":\"TRAILING\",\"separate\":true}", sign(asg, "OUTER"));
        assertEquals("{\"position\":\"LEADING\",\"separate\":true}", sign(asg, "INNER"));
        assertEquals("{\"position\":\"TRAILING\",\"separate\":false}", sign(asg, "C"));
        assertEquals("", sign(asg, "A"));
        assertEquals("", sign(asg, "B"));
        assertEquals("", sign(asg, "D"));
        assertEquals("", sign(asg, "E"));
    }

    private String sign(JsonObject asg, String name) {
        JsonObject field = findField(asg.getAsJsonArray("data_fields"), name);
        return field.has("sign") ? field.get("sign").toString() : "";
    }

    private JsonObject serializeFixture(String fixtureName) throws Exception {
        URL resource = getClass().getClassLoader().getResource("fixtures/" + fixtureName);
        Program program = new CobolParserRunnerImpl()
                .analyzeFile(new File(resource.toURI()), CobolSourceFormatEnum.FIXED);
        return AsgSerializer.serialize(program).getAsJsonArray("programs").get(0).getAsJsonObject();
    }

    private JsonObject findField(JsonArray fields, String name) {
        for (int i = 0; i < fields.size(); i++) {
            JsonObject field = fields.get(i).getAsJsonObject();
            if (name.equals(field.get("name").getAsString())) {
                return field;
            }
            if (field.has("children")) {
                JsonObject found = findField(field.getAsJsonArray("children"), name);
                if (found != null) {
                    return found;
                }
            }
        }
        return null;
    }
}
