package org.reddragon.bridge;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import io.proleap.cobol.asg.metamodel.call.Call;
import io.proleap.cobol.asg.metamodel.procedure.AtEndPhrase;
import io.proleap.cobol.asg.metamodel.procedure.NotAtEndPhrase;
import io.proleap.cobol.asg.metamodel.procedure.Statement;
import io.proleap.cobol.asg.metamodel.procedure.merge.CollatingSequencePhrase;
import io.proleap.cobol.asg.metamodel.procedure.merge.MergeStatement;
import io.proleap.cobol.asg.metamodel.procedure.merge.OutputProcedurePhrase;
import io.proleap.cobol.asg.metamodel.procedure.release.ReleaseStatement;
import io.proleap.cobol.asg.metamodel.procedure.returnstmt.ReturnStatement;
import io.proleap.cobol.asg.metamodel.procedure.sort.CollatingSequence;
import io.proleap.cobol.asg.metamodel.procedure.sort.Giving;
import io.proleap.cobol.asg.metamodel.procedure.sort.GivingPhrase;
import io.proleap.cobol.asg.metamodel.procedure.sort.InputProcedure;
import io.proleap.cobol.asg.metamodel.procedure.sort.OnKey;
import io.proleap.cobol.asg.metamodel.procedure.sort.OutputProcedure;
import io.proleap.cobol.asg.metamodel.procedure.sort.SortStatement;
import io.proleap.cobol.asg.metamodel.procedure.sort.UsingPhrase;
import java.util.List;

/** Serialises the sort-merge module's statements: SORT, MERGE, RELEASE and RETURN. */
final class SortSerializer {

    private SortSerializer() {}

    static JsonObject serializeSort(SortStatement stmt) {
        JsonObject obj = new JsonObject();
        obj.addProperty("type", "SORT");
        obj.addProperty("file_name", StatementSerializer.extractCallName(stmt.getFileCall()));
        obj.add("keys", keys(stmt.getOnKeys()));
        CollatingSequence sequence = stmt.getCollatingSequence();
        if (sequence != null) {
            addCollatingSequence(
                    obj,
                    stmt,
                    sequence.getAlphaNumeric() != null
                            ? sequence.getAlphaNumeric().getAlphabetCall()
                            : sequence.getAlphabetCalls().get(0));
        }
        obj.add("using", using(stmt.getUsingPhrases()));
        obj.add("giving", giving(stmt.getGivingPhrases()));
        InputProcedure input = stmt.getInputProcedure();
        if (input != null) {
            obj.add(
                    "input_procedure",
                    procedure(
                            input.getProcedureCall(),
                            input.getInputThrough() == null
                                    ? null
                                    : input.getInputThrough().getProcedureCall()));
        }
        OutputProcedure output = stmt.getOutputProcedure();
        if (output != null) {
            obj.add(
                    "output_procedure",
                    procedure(
                            output.getProcedureCall(),
                            output.getOutputThrough() == null
                                    ? null
                                    : output.getOutputThrough().getProcedureCall()));
        }
        return obj;
    }

    static JsonObject serializeMerge(MergeStatement stmt) {
        JsonObject obj = new JsonObject();
        obj.addProperty("type", "MERGE");
        obj.addProperty("file_name", StatementSerializer.extractCallName(stmt.getFileCall()));
        JsonArray keys = new JsonArray();
        for (io.proleap.cobol.asg.metamodel.procedure.merge.OnKey onKey : stmt.getOnKeys()) {
            for (Call keyCall : onKey.getKeyCalls()) {
                JsonObject key = new JsonObject();
                key.addProperty("direction", onKey.getOnKeyType().name());
                key.add("key", StatementSerializer.serializeRef(keyCall));
                keys.add(key);
            }
        }
        obj.add("keys", keys);
        CollatingSequencePhrase sequence = stmt.getCollatingSequencePhrase();
        if (sequence != null) {
            addCollatingSequence(
                    obj,
                    stmt,
                    sequence.getAlphaNumeric() != null
                            ? sequence.getAlphaNumeric().getAlphabetCall()
                            : sequence.getAlphabetCalls().get(0));
        }
        JsonArray using = new JsonArray();
        for (io.proleap.cobol.asg.metamodel.procedure.merge.UsingPhrase phrase : stmt.getUsingPhrases()) {
            for (Call fileCall : phrase.getFileCalls()) {
                using.add(StatementSerializer.extractCallName(fileCall));
            }
        }
        obj.add("using", using);
        JsonArray giving = new JsonArray();
        for (io.proleap.cobol.asg.metamodel.procedure.merge.GivingPhrase phrase : stmt.getGivingPhrases()) {
            for (io.proleap.cobol.asg.metamodel.procedure.merge.Giving g : phrase.getGivings()) {
                giving.add(StatementSerializer.extractCallName(g.getFileCall()));
            }
        }
        obj.add("giving", giving);
        OutputProcedurePhrase output = stmt.getOutputProcedurePhrase();
        if (output != null) {
            obj.add(
                    "output_procedure",
                    procedure(
                            output.getProcedureCall(),
                            output.getOutputThrough() == null
                                    ? null
                                    : output.getOutputThrough().getProcedureCall()));
        }
        return obj;
    }

    static JsonObject serializeRelease(ReleaseStatement stmt) {
        JsonObject obj = new JsonObject();
        obj.addProperty("type", "RELEASE");
        obj.addProperty("record_name", StatementSerializer.extractCallName(stmt.getRecordCall()));
        if (stmt.getContentCall() != null) {
            obj.add("from", StatementSerializer.serializeRef(stmt.getContentCall()));
        }
        return obj;
    }

    static JsonObject serializeReturn(ReturnStatement stmt) {
        JsonObject obj = new JsonObject();
        obj.addProperty("type", "RETURN");
        obj.addProperty("file_name", StatementSerializer.extractCallName(stmt.getFileCall()));
        if (stmt.getInto() != null && stmt.getInto().getIntoCall() != null) {
            obj.add("into", StatementSerializer.serializeRef(stmt.getInto().getIntoCall()));
        }
        AtEndPhrase atEnd = stmt.getAtEndPhrase();
        obj.add(
                "at_end",
                atEnd == null
                        ? new JsonArray()
                        : StatementSerializer.serializeStatements(atEnd.getStatements()));
        NotAtEndPhrase notAtEnd = stmt.getNotAtEndPhrase();
        obj.add(
                "not_at_end",
                notAtEnd == null
                        ? new JsonArray()
                        : StatementSerializer.serializeStatements(notAtEnd.getStatements()));
        return obj;
    }

    private static void addCollatingSequence(JsonObject obj, Statement stmt, Call alphabet) {
        JsonObject named =
                AsgSerializer.alphabetNamed(
                        stmt.getProgramUnit(), StatementSerializer.extractCallName(alphabet));
        if (named != null) {
            obj.add("collating_sequence", named);
        }
    }

    private static JsonObject procedure(Call first, Call thru) {
        JsonObject result = new JsonObject();
        result.addProperty("target", StatementSerializer.extractCallName(first));
        StatementSerializer.addProcedureSection(result, "target_section", first);
        if (thru != null) {
            result.addProperty("thru", StatementSerializer.extractCallName(thru));
            StatementSerializer.addProcedureSection(result, "thru_section", thru);
        }
        return result;
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
