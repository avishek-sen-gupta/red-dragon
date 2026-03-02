package org.reddragon.bridge;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import io.proleap.cobol.asg.metamodel.procedure.Statement;
import io.proleap.cobol.asg.metamodel.procedure.StatementType;
import io.proleap.cobol.asg.metamodel.procedure.StatementTypeEnum;
import io.proleap.cobol.asg.metamodel.procedure.add.AddStatement;
import io.proleap.cobol.asg.metamodel.procedure.add.AddToStatement;
import io.proleap.cobol.asg.metamodel.procedure.add.From;
import io.proleap.cobol.asg.metamodel.procedure.add.To;
import io.proleap.cobol.asg.metamodel.procedure.compute.ComputeStatement;
import io.proleap.cobol.asg.metamodel.procedure.compute.Store;
import io.proleap.cobol.asg.metamodel.procedure.display.DisplayStatement;
import io.proleap.cobol.asg.metamodel.procedure.display.Operand;
import io.proleap.cobol.asg.metamodel.procedure.divide.DivideStatement;
import io.proleap.cobol.asg.metamodel.procedure.divide.DivideIntoStatement;
import io.proleap.cobol.asg.metamodel.procedure.evaluate.EvaluateStatement;
import io.proleap.cobol.asg.metamodel.procedure.evaluate.WhenPhrase;
import io.proleap.cobol.asg.metamodel.procedure.gotostmt.GoToStatement;
import io.proleap.cobol.asg.metamodel.procedure.ifstmt.IfStatement;
import io.proleap.cobol.asg.metamodel.procedure.ifstmt.Then;
import io.proleap.cobol.asg.metamodel.procedure.ifstmt.Else;
import io.proleap.cobol.asg.metamodel.procedure.move.MoveStatement;
import io.proleap.cobol.asg.metamodel.procedure.move.MoveToStatement;
import io.proleap.cobol.asg.metamodel.procedure.move.MoveToSendingArea;
import io.proleap.cobol.asg.metamodel.procedure.multiply.MultiplyStatement;
import io.proleap.cobol.asg.metamodel.procedure.perform.PerformStatement;
import io.proleap.cobol.asg.metamodel.procedure.perform.PerformInlineStatement;
import io.proleap.cobol.asg.metamodel.procedure.perform.PerformProcedureStatement;
import io.proleap.cobol.asg.metamodel.procedure.perform.ByPhrase;
import io.proleap.cobol.asg.metamodel.procedure.perform.FromPhrase;
import io.proleap.cobol.asg.metamodel.procedure.perform.PerformType;
import io.proleap.cobol.asg.metamodel.procedure.perform.TestClause;
import io.proleap.cobol.asg.metamodel.procedure.perform.Times;
import io.proleap.cobol.asg.metamodel.procedure.perform.Until;
import io.proleap.cobol.asg.metamodel.procedure.perform.Varying;
import io.proleap.cobol.asg.metamodel.procedure.perform.VaryingClause;
import io.proleap.cobol.asg.metamodel.procedure.perform.VaryingPhrase;
import io.proleap.cobol.asg.metamodel.procedure.stop.StopStatement;
import io.proleap.cobol.asg.metamodel.procedure.subtract.SubtractStatement;
import io.proleap.cobol.asg.metamodel.procedure.subtract.SubtractFromStatement;
import io.proleap.cobol.asg.metamodel.procedure.subtract.Minuend;
import io.proleap.cobol.asg.metamodel.procedure.subtract.Subtrahend;
import io.proleap.cobol.asg.metamodel.call.Call;
import io.proleap.cobol.asg.metamodel.valuestmt.ValueStmt;

import java.util.List;
import java.util.logging.Logger;

/**
 * Serializes PROCEDURE DIVISION statements to JSON matching the CobolStatement contract.
 *
 * <p>Dispatches on {@code StatementType} and extracts operands, conditions,
 * and nested children for each statement type.
 */
public final class StatementSerializer {

    private static final Logger LOG = Logger.getLogger(StatementSerializer.class.getName());

    private StatementSerializer() {
    }

    /**
     * Serializes a list of statements to a JSON array.
     */
    public static JsonArray serializeStatements(List<Statement> statements) {
        JsonArray arr = new JsonArray();
        for (Statement stmt : statements) {
            JsonObject obj = serializeStatement(stmt);
            if (obj != null) {
                arr.add(obj);
            }
        }
        return arr;
    }

    /**
     * Serializes a single Statement to a CobolStatement JSON object.
     */
    public static JsonObject serializeStatement(Statement stmt) {
        StatementType stmtType = stmt.getStatementType();
        LOG.fine("Serializing statement: " + stmtType);

        if (stmtType == StatementTypeEnum.MOVE) return serializeMove((MoveStatement) stmt);
        if (stmtType == StatementTypeEnum.ADD) return serializeAdd((AddStatement) stmt);
        if (stmtType == StatementTypeEnum.SUBTRACT) return serializeSubtract((SubtractStatement) stmt);
        if (stmtType == StatementTypeEnum.MULTIPLY) return serializeMultiply((MultiplyStatement) stmt);
        if (stmtType == StatementTypeEnum.DIVIDE) return serializeDivide((DivideStatement) stmt);
        if (stmtType == StatementTypeEnum.COMPUTE) return serializeCompute((ComputeStatement) stmt);
        if (stmtType == StatementTypeEnum.IF) return serializeIf((IfStatement) stmt);
        if (stmtType == StatementTypeEnum.PERFORM) return serializePerform((PerformStatement) stmt);
        if (stmtType == StatementTypeEnum.DISPLAY) return serializeDisplay((DisplayStatement) stmt);
        if (stmtType == StatementTypeEnum.STOP) return serializeStop((StopStatement) stmt);
        if (stmtType == StatementTypeEnum.GO_TO) return serializeGoTo((GoToStatement) stmt);
        if (stmtType == StatementTypeEnum.EVALUATE) return serializeEvaluate((EvaluateStatement) stmt);

        return serializeUnknown(stmtType);
    }

    private static JsonObject serializeMove(MoveStatement stmt) {
        JsonObject obj = newStatement("MOVE");
        JsonArray operands = new JsonArray();

        MoveToStatement moveToStmt = stmt.getMoveToStatement();
        if (moveToStmt != null) {
            MoveToSendingArea sendingArea = moveToStmt.getSendingArea();
            if (sendingArea != null) {
                ValueStmt vs = sendingArea.getSendingAreaValueStmt();
                operands.add(extractValueStmtText(vs));
            }

            for (Call receivingCall : moveToStmt.getReceivingAreaCalls()) {
                operands.add(extractCallName(receivingCall));
            }
        }

        obj.add("operands", operands);
        return obj;
    }

    private static JsonObject serializeAdd(AddStatement stmt) {
        JsonObject obj = newStatement("ADD");
        JsonArray operands = new JsonArray();

        AddToStatement addTo = stmt.getAddToStatement();
        if (addTo != null) {
            for (From from : addTo.getFroms()) {
                ValueStmt vs = from.getFromValueStmt();
                operands.add(extractValueStmtText(vs));
            }
            for (To to : addTo.getTos()) {
                operands.add(extractCallName(to.getToCall()));
            }
        }

        obj.add("operands", operands);
        return obj;
    }

    private static JsonObject serializeSubtract(SubtractStatement stmt) {
        JsonObject obj = newStatement("SUBTRACT");
        JsonArray operands = new JsonArray();

        SubtractFromStatement subtractFrom = stmt.getSubtractFromStatement();
        if (subtractFrom != null) {
            for (Subtrahend sub : subtractFrom.getSubtrahends()) {
                ValueStmt vs = sub.getSubtrahendValueStmt();
                operands.add(extractValueStmtText(vs));
            }
            for (Minuend min : subtractFrom.getMinuends()) {
                operands.add(extractCallName(min.getMinuendCall()));
            }
        }

        obj.add("operands", operands);
        return obj;
    }

    private static JsonObject serializeMultiply(MultiplyStatement stmt) {
        JsonObject obj = newStatement("MULTIPLY");
        JsonArray operands = new JsonArray();
        try {
            ValueStmt operandVs = stmt.getOperandValueStmt();
            if (operandVs != null) {
                operands.add(extractValueStmtText(operandVs));
            }
        } catch (Exception e) {
            LOG.fine("Could not extract MULTIPLY operands: " + e.getMessage());
        }
        obj.add("operands", operands);
        return obj;
    }

    private static JsonObject serializeDivide(DivideStatement stmt) {
        JsonObject obj = newStatement("DIVIDE");
        JsonArray operands = new JsonArray();
        try {
            ValueStmt operandVs = stmt.getOperandValueStmt();
            if (operandVs != null) {
                operands.add(extractValueStmtText(operandVs));
            }
        } catch (Exception e) {
            LOG.fine("Could not extract DIVIDE operands: " + e.getMessage());
        }
        obj.add("operands", operands);
        return obj;
    }

    private static JsonObject serializeCompute(ComputeStatement stmt) {
        JsonObject obj = newStatement("COMPUTE");
        JsonArray operands = new JsonArray();

        // Extract arithmetic expression text
        try {
            if (stmt.getArithmeticExpression() != null && stmt.getArithmeticExpression().getCtx() != null) {
                operands.add(stmt.getArithmeticExpression().getCtx().getText());
            }
        } catch (Exception e) {
            LOG.fine("Could not extract COMPUTE expression: " + e.getMessage());
        }

        // Extract target variables
        for (Store store : stmt.getStores()) {
            Call storeCall = store.getStoreCall();
            if (storeCall != null) {
                operands.add(extractCallName(storeCall));
            }
        }

        if (operands.size() > 0) {
            obj.add("operands", operands);
        }
        return obj;
    }

    private static JsonObject serializeIf(IfStatement stmt) {
        JsonObject obj = newStatement("IF");

        // Extract condition text
        try {
            if (stmt.getCondition() != null) {
                String condText = stmt.getCondition().getCtx().getText();
                obj.addProperty("condition", insertSpaces(condText));
            }
        } catch (Exception e) {
            LOG.fine("Could not extract IF condition text: " + e.getMessage());
        }

        JsonArray children = new JsonArray();

        Then thenBlock = stmt.getThen();
        if (thenBlock != null && thenBlock.getStatements() != null) {
            for (Statement thenStmt : thenBlock.getStatements()) {
                JsonObject child = serializeStatement(thenStmt);
                if (child != null) {
                    children.add(child);
                }
            }
        }

        Else elseBlock = stmt.getElse();
        if (elseBlock != null && elseBlock.getStatements() != null) {
            for (Statement elseStmt : elseBlock.getStatements()) {
                JsonObject child = serializeStatement(elseStmt);
                if (child != null) {
                    children.add(child);
                }
            }
        }

        if (children.size() > 0) {
            obj.add("children", children);
        }

        return obj;
    }

    private static JsonObject serializePerform(PerformStatement stmt) {
        JsonObject obj = newStatement("PERFORM");
        JsonArray operands = new JsonArray();

        PerformProcedureStatement procStmt = stmt.getPerformProcedureStatement();
        if (procStmt != null) {
            List<Call> calls = procStmt.getCalls();
            if (!calls.isEmpty()) {
                // First call is the start paragraph
                operands.add(extractCallName(calls.get(0)));
            }
            // If there are >= 2 calls, last call is the THRU paragraph
            if (calls.size() >= 2) {
                obj.addProperty("thru", extractCallName(calls.get(calls.size() - 1)));
            }
            serializePerformType(procStmt.getPerformType(), obj);
        }

        if (operands.size() > 0) {
            obj.add("operands", operands);
        }

        PerformInlineStatement inlineStmt = stmt.getPerformInlineStatement();
        if (inlineStmt != null) {
            serializePerformType(inlineStmt.getPerformType(), obj);
            if (inlineStmt.getStatements() != null) {
                JsonArray children = serializeStatements(inlineStmt.getStatements());
                if (children.size() > 0) {
                    obj.add("children", children);
                }
            }
        }

        return obj;
    }

    /**
     * Serializes PerformType (TIMES / UNTIL / VARYING) fields into the statement JSON.
     */
    private static void serializePerformType(PerformType pt, JsonObject obj) {
        if (pt == null) {
            return;
        }

        try {
            PerformType.PerformTypeType typeType = pt.getPerformTypeType();
            if (typeType == null) {
                return;
            }

            if (typeType == PerformType.PerformTypeType.TIMES) {
                obj.addProperty("perform_type", "TIMES");
                Times times = pt.getTimes();
                if (times != null && times.getTimesValueStmt() != null) {
                    obj.addProperty("times", extractValueStmtText(times.getTimesValueStmt()));
                }
            } else if (typeType == PerformType.PerformTypeType.UNTIL) {
                obj.addProperty("perform_type", "UNTIL");
                Until until = pt.getUntil();
                if (until != null) {
                    serializeUntilFields(until, obj);
                }
                serializeTestClause(pt, obj);
            } else if (typeType == PerformType.PerformTypeType.VARYING) {
                obj.addProperty("perform_type", "VARYING");
                Varying varying = pt.getVarying();
                if (varying != null) {
                    VaryingClause vc = varying.getVaryingClause();
                    if (vc != null && vc.getVaryingPhrase() != null) {
                        VaryingPhrase vp = vc.getVaryingPhrase();
                        if (vp.getVaryingValueStmt() != null) {
                            obj.addProperty("varying_var", extractValueStmtText(vp.getVaryingValueStmt()));
                        }
                        if (vp.getFrom() != null && vp.getFrom().getFromValueStmt() != null) {
                            obj.addProperty("varying_from", extractValueStmtText(vp.getFrom().getFromValueStmt()));
                        }
                        if (vp.getBy() != null && vp.getBy().getByValueStmt() != null) {
                            obj.addProperty("varying_by", extractValueStmtText(vp.getBy().getByValueStmt()));
                        }
                        if (vp.getUntil() != null) {
                            serializeUntilFields(vp.getUntil(), obj);
                        }
                    }
                }
                serializeTestClause(pt, obj);
            }
        } catch (Exception e) {
            LOG.fine("Could not extract PerformType: " + e.getMessage());
        }
    }

    /**
     * Serializes Until condition fields into the JSON object.
     */
    private static void serializeUntilFields(Until until, JsonObject obj) {
        if (until.getCondition() != null && until.getCondition().getCtx() != null) {
            obj.addProperty("until", insertSpaces(until.getCondition().getCtx().getText()));
        }
    }

    /**
     * Serializes test clause (TEST BEFORE / TEST AFTER) from a PerformType.
     */
    private static void serializeTestClause(PerformType pt, JsonObject obj) {
        try {
            // Check until's test clause first, then varying's
            Until until = pt.getUntil();
            TestClause tc = null;
            if (until != null) {
                tc = until.getTestClause();
            }
            if (tc == null) {
                Varying varying = pt.getVarying();
                if (varying != null) {
                    tc = varying.getTestClause();
                }
            }
            if (tc != null && tc.getTestClauseType() != null) {
                boolean testBefore = (tc.getTestClauseType() == TestClause.TestClauseType.BEFORE);
                obj.addProperty("test_before", testBefore);
            } else {
                obj.addProperty("test_before", true); // COBOL default: TEST BEFORE
            }
        } catch (Exception e) {
            obj.addProperty("test_before", true);
        }
    }

    private static JsonObject serializeDisplay(DisplayStatement stmt) {
        JsonObject obj = newStatement("DISPLAY");
        JsonArray operands = new JsonArray();

        for (Operand operand : stmt.getOperands()) {
            ValueStmt vs = operand.getOperandValueStmt();
            operands.add(extractValueStmtText(vs));
        }

        obj.add("operands", operands);
        return obj;
    }

    private static JsonObject serializeStop(StopStatement stmt) {
        return newStatement("STOP_RUN");
    }

    private static JsonObject serializeGoTo(GoToStatement stmt) {
        JsonObject obj = newStatement("GOTO");
        JsonArray operands = new JsonArray();

        try {
            if (stmt.getSimple() != null) {
                Call procCall = stmt.getSimple().getProcedureCall();
                if (procCall != null) {
                    operands.add(extractCallName(procCall));
                }
            }
        } catch (Exception e) {
            LOG.fine("Could not extract GOTO target: " + e.getMessage());
        }

        obj.add("operands", operands);
        return obj;
    }

    private static JsonObject serializeEvaluate(EvaluateStatement stmt) {
        JsonObject obj = newStatement("EVALUATE");
        JsonArray children = new JsonArray();

        try {
            for (WhenPhrase when : stmt.getWhenPhrases()) {
                if (when.getStatements() != null) {
                    JsonArray whenStmts = serializeStatements(when.getStatements());
                    for (int i = 0; i < whenStmts.size(); i++) {
                        children.add(whenStmts.get(i));
                    }
                }
            }
        } catch (Exception e) {
            LOG.fine("Could not extract EVALUATE children: " + e.getMessage());
        }

        if (children.size() > 0) {
            obj.add("children", children);
        }

        return obj;
    }

    private static JsonObject serializeUnknown(StatementType stmtType) {
        LOG.warning("Unknown statement type: " + stmtType);
        return newStatement(stmtType.toString());
    }

    private static JsonObject newStatement(String type) {
        JsonObject obj = new JsonObject();
        obj.addProperty("type", type);
        return obj;
    }

    /**
     * Extracts a human-readable name from a ProLeap Call object.
     */
    private static String extractCallName(Call call) {
        if (call == null) {
            return "";
        }
        String name = call.getName();
        return (name != null) ? name : call.toString();
    }

    /**
     * Extracts text from a ValueStmt, falling back to ANTLR context getText().
     */
    private static String extractValueStmtText(ValueStmt vs) {
        if (vs == null) {
            return "";
        }
        try {
            if (vs.getCtx() != null) {
                return vs.getCtx().getText();
            }
        } catch (Exception e) {
            // fall through
        }
        return vs.toString();
    }

    /**
     * Inserts spaces around comparison operators from ANTLR getText() output.
     */
    private static String insertSpaces(String text) {
        if (text == null) {
            return "";
        }
        return text
                .replaceAll("(?<=[A-Za-z0-9-])([><=])", " $1")
                .replaceAll("([><=])(?=[A-Za-z0-9-])", "$1 ");
    }
}
