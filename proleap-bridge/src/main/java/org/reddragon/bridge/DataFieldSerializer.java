package org.reddragon.bridge;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import io.proleap.cobol.CobolParser;
import io.proleap.cobol.asg.metamodel.data.datadescription.DataDescriptionEntry;
import io.proleap.cobol.asg.metamodel.data.datadescription.DataDescriptionEntryCondition;
import io.proleap.cobol.asg.metamodel.data.datadescription.DataDescriptionEntryExecSql;
import io.proleap.cobol.asg.metamodel.data.datadescription.DataDescriptionEntryGroup;
import io.proleap.cobol.asg.metamodel.data.datadescription.DataDescriptionEntryRename;
import io.proleap.cobol.asg.metamodel.data.datadescription.BlankWhenZeroClause;
import io.proleap.cobol.asg.metamodel.data.datadescription.Index;
import io.proleap.cobol.asg.metamodel.data.datadescription.OccursClause;
import io.proleap.cobol.asg.metamodel.data.datadescription.OccursIndexed;
import io.proleap.cobol.asg.metamodel.data.datadescription.JustifiedClause;
import io.proleap.cobol.asg.metamodel.data.datadescription.SignClause;
import io.proleap.cobol.asg.metamodel.data.datadescription.SynchronizedClause;
import io.proleap.cobol.asg.metamodel.data.datadescription.ValueInterval;
import io.proleap.cobol.asg.metamodel.valuestmt.ValueStmt;

import java.util.ArrayList;
import java.util.List;
import java.util.logging.Logger;

/**
 * Serializes DATA DIVISION entries to JSON matching the CobolField contract.
 *
 * <p>Emits structure only: the ASG reader (cobol_asg/storage_layout.py)
 * computes every offset and size.
 */
public final class DataFieldSerializer {

    private static final Logger LOG = Logger.getLogger(DataFieldSerializer.class.getName());


    /** Running counter for disambiguating FILLER fields within a serialization session. */
    private int fillerCount = 0;

    private DataFieldSerializer() {
    }

    /**
     * Serializes a list of top-level data entries (e.g. Working-Storage root entries).
     *
     * @param entries top-level DataDescriptionEntry list
     * @return JSON array of CobolField objects
     */
    public static JsonArray serializeEntries(List<DataDescriptionEntry> entries) {
        DataFieldSerializer instance = new DataFieldSerializer();
        JsonArray fields = new JsonArray();

        for (DataDescriptionEntry entry : entries) {
            if (entry instanceof DataDescriptionEntryGroup group) {
                fields.add(instance.serializeGroup(group));
            } else if (entry instanceof DataDescriptionEntryRename rename) {
                fields.add(instance.serializeRename(rename));
            } else if (entry instanceof DataDescriptionEntryExecSql) {
                // Deliberately not serialized here: it has no storage and does
                // not belong in data_fields. Collected separately by
                // serializeExecSqlEntries (forge-qhi) -- see AsgSerializer's
                // "data_division_exec_sql" key. Named explicitly (not folded
                // into the else below) so it is never mistaken for the
                // unhandled-type case that else logs.
            } else {
                // Anything else is a ProLeap entry kind this serializer does
                // not yet know about. This is the exact trap forge-qhi found:
                // EXEC_SQL fell off the end of this chain silently -- no
                // error, no JSON node -- for years. Log loudly instead of
                // repeating that history for the next new kind.
                LOG.warning("Unhandled DataDescriptionEntry subtype: "
                        + entry.getClass().getName() + " -- dropped from data_fields");
            }
        }
        return fields;
    }

    /** Serializes the records of one FD. */
    public static JsonArray serializeRecordArea(List<DataDescriptionEntry> records) {
        DataFieldSerializer instance = new DataFieldSerializer();
        JsonArray fields = new JsonArray();
        for (DataDescriptionEntry entry : records) {
            if (entry instanceof DataDescriptionEntryGroup group) {
                fields.add(instance.serializeGroup(group));
            } else if (entry instanceof DataDescriptionEntryRename rename) {
                fields.add(instance.serializeRename(rename));
            } else if (!(entry instanceof DataDescriptionEntryExecSql)) {
                LOG.warning("Unhandled DataDescriptionEntry subtype: "
                        + entry.getClass().getName() + " -- dropped from file_fields");
            }
        }
        return fields;
    }

    /**
     * Recursively collects every EXEC SQL data-description entry (e.g. a
     * DECLARE CURSOR written in WORKING-STORAGE rather than PROCEDURE
     * DIVISION) found anywhere under {@code entries}, including nested
     * inside group children. ProLeap already builds this node and populates
     * its text via {@link DataDescriptionEntryExecSql#getExecSqlText()};
     * {@link #serializeEntries} silently drops it because it carries no
     * storage. Each is tagged with which DATA DIVISION section it came from,
     * so the Python side can tell a WORKING-STORAGE declare from a LINKAGE
     * one without re-deriving that from source spans.
     *
     * @param entries root or child DataDescriptionEntry list to search
     * @param section the DATA DIVISION section name this list came from
     *                (e.g. "WORKING-STORAGE", "LINKAGE", "LOCAL-STORAGE")
     * @return JSON array of {section, exec_sql_text, line_start, col_start,
     *         line_end, col_end} objects, in source order
     */
    public static JsonArray serializeExecSqlEntries(List<DataDescriptionEntry> entries, String section) {
        JsonArray out = new JsonArray();
        collectExecSqlEntries(entries, section, out);
        return out;
    }

    private static void collectExecSqlEntries(
            List<DataDescriptionEntry> entries, String section, JsonArray out) {
        if (entries == null) {
            return;
        }
        for (DataDescriptionEntry entry : entries) {
            if (entry instanceof DataDescriptionEntryExecSql execSql) {
                String text = execSql.getExecSqlText();
                if (text == null) {
                    // A null here would reach Python as None and crash
                    // parse_exec_sql at compile time -- skip and log loudly
                    // rather than emit a node the consumer cannot use.
                    LOG.warning("DataDescriptionEntryExecSql with null exec_sql_text -- skipped");
                    continue;
                }
                JsonObject obj = new JsonObject();
                obj.addProperty("section", section);
                obj.addProperty("exec_sql_text", text);
                StatementSerializer.addSpan(obj, execSql.getCtx());
                out.add(obj);
            } else if (entry instanceof DataDescriptionEntryGroup group) {
                collectExecSqlEntries(group.getDataDescriptionEntries(), section, out);
            } else {
                // Rename/Condition entries cannot themselves carry a nested
                // EXEC SQL entry, but logging here (rather than silently
                // matching nothing) means a future ProLeap entry kind that
                // COULD nest one does not repeat forge-qhi's silent-drop trap.
                LOG.fine("collectExecSqlEntries: not recursing into "
                        + entry.getClass().getName());
            }
        }
    }

    /**
     * Serializes a single DataDescriptionEntryGroup to a CobolField JSON object.
     */
    private JsonObject serializeGroup(DataDescriptionEntryGroup group) {
        JsonObject obj = new JsonObject();
        String fieldName = disambiguateFiller(group.getName());
        obj.addProperty("name", fieldName);
        if (isFiller(group.getName())) {
            obj.addProperty("filler", true);
        }
        obj.addProperty("level", group.getLevelNumber());
        obj.addProperty("pic", extractPic(group));
        String usage = extractUsage(group);
        if (usage != null) {
            obj.addProperty("usage", usage);
        }
        StatementSerializer.addSpan(obj, group.getCtx());

        String value = extractFirstValue(group);
        if (!value.isEmpty()) {
            obj.addProperty("value", value);
        }
        // Distinguish a figurative VALUE (SPACES, ZEROS, ...) — which fills the
        // whole field with its fill character — from a quoted literal that merely
        // looks like one (VALUE 'SPACE'). The figurative keyword is never quoted
        // in source (red-dragon-zuhj).
        if (isFigurativeValue(group)) {
            obj.addProperty("value_is_figurative", true);
        }
        if (isAllValue(group)) {
            obj.addProperty("value_is_all", true);
        }
        if (isNumericValue(group)) {
            obj.addProperty("value_is_numeric", true);
        }

        JsonArray valuesArray = extractAllValues(group);
        if (valuesArray.size() > 0) {
            obj.add("values", valuesArray);
        }

        String redefines = extractRedefines(group);
        if (!redefines.isEmpty()) {
            obj.addProperty("redefines", redefines);
        }

        int occursCount = extractOccurs(group);
        if (occursCount > 0) {
            obj.addProperty("occurs", occursCount);
        }

        List<String> indexNames = extractIndexNames(group);
        if (!indexNames.isEmpty()) {
            JsonArray arr = new JsonArray();
            for (String n : indexNames) {
                arr.add(n);
            }
            obj.add("indexed_by", arr);
        }

        int occursMin = extractOccursMin(group);
        if (occursMin > 0) {
            obj.addProperty("occurs_min", occursMin);
        }

        JsonObject dependingOn = extractOccursDependingOn(group);
        if (dependingOn != null) {
            obj.add("occurs_depending_on", dependingOn);
        }

        JsonObject signObj = extractSign(group);
        if (signObj != null) {
            obj.add("sign", signObj);
        }

        if (extractJustified(group)) {
            obj.addProperty("justified_right", true);
        }

        if (extractSynchronized(group)) {
            obj.addProperty("synchronized", true);
        }

        if (extractBlankWhenZero(group)) {
            obj.addProperty("blank_when_zero", true);
        }

        if (group.getExternalClause() != null) {
            obj.addProperty("external", true);
        }

        List<DataDescriptionEntry> children = group.getDataDescriptionEntries();
        if (children != null && !children.isEmpty()) {
            JsonArray childArray = serializeChildren(children);
            if (childArray.size() > 0) {
                obj.add("children", childArray);
            }

            JsonArray conditionsArray = serializeConditions(children);
            if (conditionsArray.size() > 0) {
                obj.add("conditions", conditionsArray);
            }
        }

        LOG.fine("Serialized field: " + fieldName + " level=" + group.getLevelNumber()
                + " pic=" + extractPic(group));
        return obj;
    }

    /**
     * Serializes a level-66 RENAMES entry to a CobolField JSON object.
     * The renamed items are structured references, OF/IN qualifiers included.
     */
    private JsonObject serializeRename(DataDescriptionEntryRename rename) {
        JsonObject obj = new JsonObject();
        String fieldName = disambiguateFiller(rename.getName());
        obj.addProperty("name", fieldName);
        obj.addProperty("level", 66);
        obj.addProperty("pic", "");
        obj.addProperty("usage", "DISPLAY");
        StatementSerializer.addSpan(obj, rename.getCtx());

        if (rename.getRenamesClause() != null) {
            if (rename.getRenamesClause().getFrom() != null) {
                obj.add("renames_from",
                        StatementSerializer.serializeRef(rename.getRenamesClause().getFrom()));
            }
            if (rename.getRenamesClause().getTo() != null) {
                obj.add("renames_thru",
                        StatementSerializer.serializeRef(rename.getRenamesClause().getTo()));
            }
        }

        LOG.fine("Serialized RENAMES field: " + fieldName);
        return obj;
    }

    /**
     * Disambiguates FILLER field names by appending a sequential counter.
     * "FILLER" becomes "FILLER_1", "FILLER_2", etc.
     */
    private static boolean isFiller(String name) {
        return name == null || "FILLER".equalsIgnoreCase(name);
    }

    private String disambiguateFiller(String name) {
        if (isFiller(name)) {
            fillerCount++;
            return "FILLER_" + fillerCount;
        }
        return name;
    }

    /** Serializes child entries in order. */
    private JsonArray serializeChildren(List<DataDescriptionEntry> children) {
        JsonArray childArray = new JsonArray();
        for (DataDescriptionEntry child : children) {
            if (child instanceof DataDescriptionEntryGroup childGroup) {
                childArray.add(serializeGroup(childGroup));
            } else if (child instanceof DataDescriptionEntryRename rename) {
                childArray.add(serializeRename(rename));
            }
        }
        return childArray;
    }

    /**
     * Serializes level-88 condition entries from a list of children.
     * Returns a JSON array of condition objects, each with "name" and "values".
     */
    private JsonArray serializeConditions(List<DataDescriptionEntry> children) {
        JsonArray conditionsArray = new JsonArray();

        for (DataDescriptionEntry child : children) {
            if (child instanceof DataDescriptionEntryCondition condition) {
                JsonObject condObj = new JsonObject();
                condObj.addProperty("name", condition.getName());

                JsonArray valuesArray = new JsonArray();
                try {
                    if (condition.getValueClause() != null
                            && condition.getValueClause().getValueIntervals() != null) {
                        for (ValueInterval interval : condition.getValueClause().getValueIntervals()) {
                            valuesArray.add(serializeValueInterval(interval));
                        }
                    }
                } catch (Exception e) {
                    LOG.fine("Could not extract values for condition " + condition.getName()
                            + ": " + e.getMessage());
                }

                condObj.add("values", valuesArray);
                conditionsArray.add(condObj);
                LOG.fine("Serialized level-88 condition: " + condition.getName()
                        + " with " + valuesArray.size() + " value intervals");
            }
        }
        return conditionsArray;
    }

    /**
     * Serializes a single ValueInterval: its "from" and "to" literals as
     * written, and which kind of literal it is.
     */
    private static JsonObject serializeValueInterval(ValueInterval interval) {
        JsonObject intervalObj = new JsonObject();

        intervalObj.addProperty("from", rawBoundText(fromLiteral(interval), interval.getFromValueStmt()));
        intervalObj.addProperty("to", rawBoundText(toLiteral(interval), interval.getToValueStmt()));
        if (isAllLiteral(fromLiteral(interval))) {
            intervalObj.addProperty("all", true);
        }
        if (isNumericLiteral(fromLiteral(interval))) {
            intervalObj.addProperty("numeric", true);
        }
        if (isFigurativeLiteral(fromLiteral(interval))) {
            intervalObj.addProperty("figurative", true);
        }
        return intervalObj;
    }

    private static boolean isFigurativeLiteral(CobolParser.LiteralContext lit) {
        return lit != null && unwrapAll(lit).figurativeConstant() != null;
    }

    private static boolean isNumericLiteral(CobolParser.LiteralContext lit) {
        return lit != null && unwrapAll(lit).numericLiteral() != null;
    }

    private static CobolParser.LiteralContext fromLiteral(ValueInterval interval) {
        return interval.getCtx() instanceof CobolParser.DataValueIntervalContext ctx
                ? ctx.dataValueIntervalFrom().literal() : null;
    }

    private static CobolParser.LiteralContext toLiteral(ValueInterval interval) {
        return interval.getCtx() instanceof CobolParser.DataValueIntervalContext ctx
                && ctx.dataValueIntervalTo() != null
                ? ctx.dataValueIntervalTo().literal() : null;
    }

    private static CobolParser.LiteralContext unwrapAll(CobolParser.LiteralContext lit) {
        CobolParser.LiteralContext repeated = StatementSerializer.allRepeatedLiteral(lit);
        return repeated != null ? unwrapAll(repeated) : lit;
    }

    private static String rawBoundText(CobolParser.LiteralContext lit, ValueStmt vs) {
        if (lit != null) {
            return unwrapAll(lit).getText();
        }
        return vs != null && vs.getCtx() != null ? vs.getCtx().getText() : "";
    }

    private static boolean isAllLiteral(CobolParser.LiteralContext lit) {
        return StatementSerializer.allRepeatedLiteral(lit) != null
                && unwrapAll(lit).figurativeConstant() == null;
    }

    private static boolean isAllValue(DataDescriptionEntryGroup group) {
        return group.getValueClause() != null
                && !group.getValueClause().getValueIntervals().isEmpty()
                && isAllLiteral(fromLiteral(group.getValueClause().getValueIntervals().get(0)));
    }

    /**
     * True when the item's VALUE is a numeric literal: an edited item edits a
     * numeric VALUE as a MOVE would, but stores a nonnumeric one verbatim.
     * The figurative ZERO is not a numeric literal.
     */
    private static boolean isNumericValue(DataDescriptionEntryGroup group) {
        if (group.getValueClause() == null
                || group.getValueClause().getValueIntervals().isEmpty()) {
            return false;
        }
        CobolParser.LiteralContext lit =
                fromLiteral(group.getValueClause().getValueIntervals().get(0));
        CobolParser.NumericLiteralContext numeric =
                lit == null ? null : unwrapAll(lit).numericLiteral();
        return numeric != null && numeric.ZERO() == null;
    }

    private static String extractPic(DataDescriptionEntryGroup group) {
        try {
            if (group.getPictureClause() != null) {
                return group.getPictureClause().getPictureString();
            }
        } catch (Exception e) {
            LOG.fine("No PIC clause for " + group.getName());
        }
        return "";
    }

    /**
     * The entry's own USAGE clause as ProLeap's ASG names it (its
     * UsageClauseType, e.g. PACKED_DECIMAL), or null when it has none. The ASG
     * reader reads the synonyms as one USAGE and applies a group's USAGE to the
     * items in it.
     */
    private static String extractUsage(DataDescriptionEntryGroup group) {
        if (group.getUsageClause() != null && group.getUsageClause().getUsageClauseType() != null) {
            return group.getUsageClause().getUsageClauseType().name();
        }
        return null;
    }

    /**
     * Extracts the first value from a VALUE clause (backward compatibility).
     */
    private static String extractFirstValue(DataDescriptionEntryGroup group) {
        try {
            if (group.getValueClause() != null && !group.getValueClause().getValueIntervals().isEmpty()) {
                ValueInterval interval = group.getValueClause().getValueIntervals().get(0);
                return rawBoundText(fromLiteral(interval), interval.getFromValueStmt());
            }
        } catch (Exception e) {
            LOG.fine("No VALUE clause for " + group.getName());
        }
        return "";
    }

    private static final java.util.Set<String> FIGURATIVE_KEYWORDS = java.util.Set.of(
            "SPACE", "SPACES", "ZERO", "ZEROS", "ZEROES", "QUOTE", "QUOTES",
            "LOW-VALUE", "LOW-VALUES", "HIGH-VALUE", "HIGH-VALUES");

    /**
     * True when the group's VALUE clause is an (unquoted) figurative constant,
     * as opposed to a quoted literal. The raw source text is inspected before
     * quote stripping so VALUE 'SPACE' is NOT treated as figurative.
     */
    private static boolean isFigurativeValue(DataDescriptionEntryGroup group) {
        try {
            if (group.getValueClause() != null
                    && !group.getValueClause().getValueIntervals().isEmpty()) {
                ValueInterval interval = group.getValueClause().getValueIntervals().get(0);
                String raw = rawBoundText(fromLiteral(interval), interval.getFromValueStmt());
                boolean quoted = raw.length() >= 2
                        && ((raw.startsWith("'") && raw.endsWith("'"))
                        || (raw.startsWith("\"") && raw.endsWith("\"")));
                return !quoted && FIGURATIVE_KEYWORDS.contains(raw.toUpperCase());
            }
        } catch (Exception e) {
            LOG.fine("Could not determine figurative VALUE for " + group.getName());
        }
        return false;
    }

    /**
     * Extracts all value intervals from a VALUE clause as a JSON array
     * of {"from": ..., "to": ...} objects.
     */
    private static JsonArray extractAllValues(DataDescriptionEntryGroup group) {
        JsonArray valuesArray = new JsonArray();
        try {
            if (group.getValueClause() != null
                    && group.getValueClause().getValueIntervals() != null
                    && !group.getValueClause().getValueIntervals().isEmpty()) {
                for (ValueInterval interval : group.getValueClause().getValueIntervals()) {
                    valuesArray.add(serializeValueInterval(interval));
                }
            }
        } catch (Exception e) {
            LOG.fine("Could not extract all values for " + group.getName());
        }
        return valuesArray;
    }

    private static String extractRedefines(DataDescriptionEntryGroup group) {
        try {
            if (group.getRedefinesClause() != null) {
                return group.getRedefinesClause().getRedefinesCall().getName();
            }
        } catch (Exception e) {
            LOG.fine("No REDEFINES clause for " + group.getName());
        }
        return "";
    }

    /**
     * Extracts the SYNCHRONIZED clause from a data description entry.
     * Returns true if SYNCHRONIZED is present.
     */
    private static boolean extractSynchronized(DataDescriptionEntryGroup group) {
        try {
            SynchronizedClause syncClause = group.getSynchronizedClause();
            return syncClause != null;
        } catch (Exception e) {
            LOG.fine("No SYNCHRONIZED clause for " + group.getName());
        }
        return false;
    }

    /**
     * Extracts the JUSTIFIED clause from a data description entry.
     * Returns true if JUSTIFIED RIGHT is present.
     */
    private static boolean extractJustified(DataDescriptionEntryGroup group) {
        try {
            JustifiedClause justifiedClause = group.getJustifiedClause();
            return justifiedClause != null;
        } catch (Exception e) {
            LOG.fine("No JUSTIFIED clause for " + group.getName());
        }
        return false;
    }

    /**
     * Extracts the BLANK WHEN ZERO clause from a data description entry.
     * Returns true if BLANK WHEN ZERO is present.
     */
    private static boolean extractBlankWhenZero(DataDescriptionEntryGroup group) {
        try {
            BlankWhenZeroClause blankClause = group.getBlankWhenZeroClause();
            return blankClause != null;
        } catch (Exception e) {
            LOG.fine("No BLANK WHEN ZERO clause for " + group.getName());
        }
        return false;
    }

    /**
     * The entry's own SIGN clause as a JSON object with "position"
     * ("LEADING"/"TRAILING") and "separate" (boolean), or null when it has none.
     * The ASG reader applies a group's clause to its subordinates.
     */
    private static JsonObject extractSign(DataDescriptionEntryGroup group) {
        SignClause own = group.getSignClause();
        return own != null && own.getSignClauseType() != null ? signJson(own) : null;
    }

    private static JsonObject signJson(SignClause signClause) {
        JsonObject signObj = new JsonObject();
        String position = signClause.getSignClauseType() == SignClause.SignClauseType.LEADING
                ? "LEADING" : "TRAILING";
        signObj.addProperty("position", position);
        signObj.addProperty("separate", signClause.isSeparate());
        return signObj;
    }

    /**
     * Extracts the OCCURS count from a data description entry.
     * For OCCURS DEPENDING ON, returns the max count (from getTo()).
     * For fixed OCCURS, returns getFrom() (the only count).
     * Returns 0 if no OCCURS clause is present.
     */
    private static int extractOccurs(DataDescriptionEntryGroup group) {
        try {
            List<OccursClause> occursClauses = group.getOccursClauses();
            if (occursClauses != null && !occursClauses.isEmpty()) {
                OccursClause clause = occursClauses.get(0);
                // If DEPENDING ON is present, getTo() is the max count
                if (clause.getOccursDepending() != null && clause.getTo() != null) {
                    return Integer.parseInt(clause.getTo().getCtx().getText());
                }
                // Fixed OCCURS: the count is in getFrom()
                if (clause.getFrom() != null && clause.getFrom().getCtx() != null) {
                    return Integer.parseInt(clause.getFrom().getCtx().getText());
                }
            }
        } catch (Exception e) {
            LOG.fine("Could not extract OCCURS for " + group.getName() + ": " + e.getMessage());
        }
        return 0;
    }

    /**
     * The INDEXED BY names on a group's OccursClause, in declaration order.
     *
     * <p>An index declared this way is compiler-allocated: there is deliberately no
     * `01 IX PIC ...` anywhere, so this clause is the item's only declaration. Order
     * matters — a Format 1 SEARCH with no VARYING advances the FIRST index. Names are
     * preserved verbatim as declared, matching every other identifier extractor in
     * this class (e.g. {@code extractRedefines}, {@code extractOccursDependingOn}) —
     * case-insensitive matching is done by callers, not by upper-casing here.
     */
    private static List<String> extractIndexNames(DataDescriptionEntryGroup group) {
        List<String> names = new ArrayList<>();
        try {
            List<OccursClause> clauses = group.getOccursClauses();
            if (clauses == null || clauses.isEmpty()) {
                return names;
            }
            OccursIndexed indexed = clauses.get(0).getOccursIndexed();
            if (indexed == null || indexed.getIndices() == null) {
                return names;
            }
            for (Index ix : indexed.getIndices()) {
                if (ix.getName() != null) {
                    names.add(ix.getName());
                }
            }
        } catch (Exception e) {
            LOG.fine("No INDEXED BY names: " + e.getMessage());
        }
        return names;
    }

    /**
     * Extracts the minimum OCCURS count for OCCURS DEPENDING ON.
     * Returns 0 if no DEPENDING ON clause or no minimum specified.
     */
    private static int extractOccursMin(DataDescriptionEntryGroup group) {
        try {
            List<OccursClause> occursClauses = group.getOccursClauses();
            if (occursClauses != null && !occursClauses.isEmpty()) {
                OccursClause clause = occursClauses.get(0);
                if (clause.getOccursDepending() != null
                        && clause.getFrom() != null
                        && clause.getFrom().getCtx() != null) {
                    return Integer.parseInt(clause.getFrom().getCtx().getText());
                }
            }
        } catch (Exception e) {
            LOG.fine("Could not extract OCCURS min for " + group.getName() + ": " + e.getMessage());
        }
        return 0;
    }

    /**
     * Extracts the DEPENDING ON object of an OCCURS clause as a structured
     * reference, OF/IN qualifiers included. Returns null if no DEPENDING ON
     * clause is present.
     */
    private static JsonObject extractOccursDependingOn(DataDescriptionEntryGroup group) {
        try {
            List<OccursClause> occursClauses = group.getOccursClauses();
            if (occursClauses != null && !occursClauses.isEmpty()) {
                OccursClause clause = occursClauses.get(0);
                if (clause.getOccursDepending() != null
                        && clause.getOccursDepending().getDependingOnCall() != null) {
                    return StatementSerializer.serializeRef(
                            clause.getOccursDepending().getDependingOnCall());
                }
            }
        } catch (Exception e) {
            LOG.fine("Could not extract DEPENDING ON for " + group.getName() + ": " + e.getMessage());
        }
        return null;
    }
}
