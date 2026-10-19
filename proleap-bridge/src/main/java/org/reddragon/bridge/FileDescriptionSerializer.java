package org.reddragon.bridge;

import com.google.gson.JsonObject;
import io.proleap.cobol.CobolParser;
import io.proleap.cobol.asg.metamodel.data.file.FileDescriptionEntry;
import io.proleap.cobol.asg.metamodel.data.file.LinageClause;
import io.proleap.cobol.asg.metamodel.data.file.RecordContainsClause;
import io.proleap.cobol.asg.metamodel.IntegerLiteral;

/** Serialises an FD's RECORDING MODE, RECORD, EXTERNAL, GLOBAL and LINAGE clauses: the facts its record format, its logical page and its file connector's and file-name's scope are derived from. */
final class FileDescriptionSerializer {

    private FileDescriptionSerializer() {}

    static JsonObject serialize(FileDescriptionEntry fd) {
        JsonObject result = new JsonObject();
        result.addProperty("fd_name", fd.getName());
        result.addProperty("recording_mode", recordingMode(fd));
        result.addProperty("external", fd.getExternalClause() != null);
        result.addProperty("global", fd.getGlobalClause() != null);
        result.add("record_clause", recordClause(fd.getRecordContainsClause()));
        if (fd.getLinageClause() != null) {
            result.add("linage", linage(fd.getLinageClause()));
        }
        return result;
    }

    /** The LINAGE clause's operands as written; a phrase not written is absent. */
    private static JsonObject linage(LinageClause clause) {
        JsonObject result = new JsonObject();
        result.add("lines", StatementSerializer.serializeFromValue(clause.getNumberOfLinesValueStmt()));
        if (clause.getFootingAtValueStmt() != null) {
            result.add("footing", StatementSerializer.serializeFromValue(clause.getFootingAtValueStmt()));
        }
        if (clause.getLinesAtTopValueStmt() != null) {
            result.add("top", StatementSerializer.serializeFromValue(clause.getLinesAtTopValueStmt()));
        }
        if (clause.getLinesAtBottomValueStmt() != null) {
            result.add("bottom", StatementSerializer.serializeFromValue(clause.getLinesAtBottomValueStmt()));
        }
        return result;
    }

    private static String recordingMode(FileDescriptionEntry fd) {
        CobolParser.FileDescriptionEntryContext ctx =
                (CobolParser.FileDescriptionEntryContext) fd.getCtx();
        for (CobolParser.FileDescriptionEntryClauseContext clause : ctx.fileDescriptionEntryClause()) {
            if (clause.recordingModeClause() != null) {
                return clause.recordingModeClause().modeStatement().getText().toUpperCase();
            }
        }
        return "";
    }

    private static JsonObject recordClause(RecordContainsClause clause) {
        JsonObject result = new JsonObject();
        if (clause == null) {
            result.addProperty("kind", "none");
        } else if (clause.isVarying()) {
            result.addProperty("kind", "varying");
            result.addProperty("minimum", size(clause.getFrom()));
            result.addProperty("maximum", size(clause.getTo()));
            result.addProperty(
                    "depending_on",
                    clause.getDependingOnCall() == null ? "" : clause.getDependingOnCall().getName());
        } else if (clause.getTo() != null) {
            result.addProperty("kind", "range");
            result.addProperty("minimum", size(clause.getFrom()));
            result.addProperty("maximum", size(clause.getTo()));
        } else {
            result.addProperty("kind", "contains");
            result.addProperty("size", size(clause.getFrom()));
        }
        return result;
    }

    private static int size(IntegerLiteral literal) {
        return literal == null ? 0 : literal.getValue().intValue();
    }
}
