package org.reddragon.bridge;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import io.proleap.cobol.asg.metamodel.call.Call;
import io.proleap.cobol.asg.metamodel.procedure.sort.Giving;
import io.proleap.cobol.asg.metamodel.procedure.sort.GivingPhrase;
import io.proleap.cobol.asg.metamodel.procedure.sort.OnKey;
import io.proleap.cobol.asg.metamodel.procedure.sort.SortStatement;
import io.proleap.cobol.asg.metamodel.procedure.sort.UsingPhrase;
import java.util.List;

/** Serialises the sort-merge module's statements: SORT. */
final class SortSerializer {

    private SortSerializer() {}

    static JsonObject serializeSort(SortStatement stmt) {
        JsonObject obj = new JsonObject();
        obj.addProperty("type", "SORT");
        obj.addProperty("file_name", StatementSerializer.extractCallName(stmt.getFileCall()));
        obj.add("keys", keys(stmt.getOnKeys()));
        obj.add("using", using(stmt.getUsingPhrases()));
        obj.add("giving", giving(stmt.getGivingPhrases()));
        return obj;
    }

    private static JsonArray keys(List<OnKey> onKeys) {
        JsonArray result = new JsonArray();
        for (OnKey onKey : onKeys) {
            for (Call keyCall : onKey.getKeyCalls()) {
                JsonObject key = new JsonObject();
                key.addProperty("direction", onKey.getOnKeyType().name());
                key.add("key", StatementSerializer.serializeRef(keyCall));
                result.add(key);
            }
        }
        return result;
    }

    private static JsonArray using(List<UsingPhrase> phrases) {
        JsonArray result = new JsonArray();
        for (UsingPhrase phrase : phrases) {
            for (Call fileCall : phrase.getFileCalls()) {
                result.add(StatementSerializer.extractCallName(fileCall));
            }
        }
        return result;
    }

    private static JsonArray giving(List<GivingPhrase> phrases) {
        JsonArray result = new JsonArray();
        for (GivingPhrase phrase : phrases) {
            for (Giving giving : phrase.getGivings()) {
                result.add(StatementSerializer.extractCallName(giving.getFileCall()));
            }
        }
        return result;
    }
}
