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
import io.proleap.cobol.asg.metamodel.procedure.continuestmt.ContinueStatement;
import io.proleap.cobol.asg.metamodel.procedure.display.DisplayStatement;
import io.proleap.cobol.asg.metamodel.procedure.display.Operand;
import io.proleap.cobol.asg.metamodel.procedure.divide.DivideByGivingStatement;
import io.proleap.cobol.asg.metamodel.procedure.divide.DivideIntoGivingStatement;
import io.proleap.cobol.asg.metamodel.procedure.divide.DivideIntoStatement;
import io.proleap.cobol.asg.metamodel.procedure.divide.DivideStatement;
import io.proleap.cobol.asg.metamodel.procedure.divide.Giving;
import io.proleap.cobol.asg.metamodel.procedure.divide.GivingPhrase;
import io.proleap.cobol.asg.metamodel.procedure.divide.Into;
import io.proleap.cobol.asg.metamodel.procedure.evaluate.EvaluateStatement;
import io.proleap.cobol.asg.metamodel.procedure.evaluate.WhenPhrase;
import io.proleap.cobol.asg.metamodel.procedure.exit.ExitStatement;
import io.proleap.cobol.asg.metamodel.procedure.gotostmt.GoToStatement;
import io.proleap.cobol.asg.metamodel.procedure.ifstmt.IfStatement;
import io.proleap.cobol.asg.metamodel.procedure.ifstmt.Then;
import io.proleap.cobol.asg.metamodel.procedure.ifstmt.Else;
import io.proleap.cobol.asg.metamodel.procedure.initialize.InitializeStatement;
import io.proleap.cobol.asg.metamodel.procedure.inspect.AllLeading;
import io.proleap.cobol.asg.metamodel.procedure.inspect.AllLeadingPhrase;
import io.proleap.cobol.asg.metamodel.procedure.inspect.InspectStatement;
import io.proleap.cobol.asg.metamodel.procedure.inspect.ReplacingAllLeading;
import io.proleap.cobol.asg.metamodel.procedure.inspect.ReplacingAllLeadings;
import io.proleap.cobol.asg.metamodel.procedure.open.OpenStatement;
import io.proleap.cobol.asg.metamodel.procedure.read.ReadStatement;
import io.proleap.cobol.asg.metamodel.procedure.search.SearchStatement;
import io.proleap.cobol.asg.metamodel.procedure.alter.AlterStatement;
import io.proleap.cobol.asg.metamodel.procedure.alter.ProceedTo;
import io.proleap.cobol.asg.metamodel.procedure.call.CallStatement;
import io.proleap.cobol.asg.metamodel.procedure.call.UsingParameter;
import io.proleap.cobol.asg.metamodel.procedure.accept.AcceptStatement;
import io.proleap.cobol.asg.metamodel.procedure.cancel.CancelStatement;
import io.proleap.cobol.asg.metamodel.procedure.close.CloseStatement;
import io.proleap.cobol.asg.metamodel.procedure.entry.EntryStatement;
import io.proleap.cobol.asg.metamodel.procedure.move.MoveStatement;
import io.proleap.cobol.asg.metamodel.procedure.move.MoveToStatement;
import io.proleap.cobol.asg.metamodel.procedure.move.MoveToSendingArea;
import io.proleap.cobol.asg.metamodel.procedure.multiply.ByOperand;
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
import io.proleap.cobol.asg.metamodel.procedure.set.SetBy;
import io.proleap.cobol.asg.metamodel.procedure.set.SetStatement;
import io.proleap.cobol.asg.metamodel.procedure.set.SetTo;
import io.proleap.cobol.asg.metamodel.procedure.stop.StopStatement;
import io.proleap.cobol.asg.metamodel.procedure.string.DelimitedByPhrase;
import io.proleap.cobol.asg.metamodel.procedure.string.Sendings;
import io.proleap.cobol.asg.metamodel.procedure.string.StringStatement;
import io.proleap.cobol.asg.metamodel.procedure.subtract.SubtractStatement;
import io.proleap.cobol.asg.metamodel.procedure.subtract.SubtractFromStatement;
import io.proleap.cobol.asg.metamodel.procedure.subtract.Minuend;
import io.proleap.cobol.asg.metamodel.procedure.subtract.Subtrahend;
import io.proleap.cobol.asg.metamodel.procedure.unstring.UnstringStatement;
import io.proleap.cobol.asg.metamodel.procedure.write.WriteStatement;
import io.proleap.cobol.asg.metamodel.call.Call;
import io.proleap.cobol.asg.metamodel.valuestmt.ValueStmt;

import org.antlr.v4.runtime.CharStream;
import org.antlr.v4.runtime.Token;
import org.antlr.v4.runtime.misc.Interval;

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
        if (stmtType == StatementTypeEnum.CONTINUE) return serializeContinue((ContinueStatement) stmt);
        if (stmtType == StatementTypeEnum.EXIT) return serializeExit((ExitStatement) stmt);
        if (stmtType == StatementTypeEnum.INITIALIZE) return serializeInitialize((InitializeStatement) stmt);
        if (stmtType == StatementTypeEnum.SET) return serializeSet((SetStatement) stmt);
        if (stmtType == StatementTypeEnum.STRING) return serializeString((StringStatement) stmt);
        if (stmtType == StatementTypeEnum.UNSTRING) return serializeUnstring((UnstringStatement) stmt);
        if (stmtType == StatementTypeEnum.INSPECT) return serializeInspect((InspectStatement) stmt);
        if (stmtType == StatementTypeEnum.SEARCH) return serializeSearch((SearchStatement) stmt);
        if (stmtType == StatementTypeEnum.CALL) return serializeCall((CallStatement) stmt);
        if (stmtType == StatementTypeEnum.ALTER) return serializeAlter((AlterStatement) stmt);
        if (stmtType == StatementTypeEnum.ENTRY) return serializeEntry((EntryStatement) stmt);
        if (stmtType == StatementTypeEnum.CANCEL) return serializeCancel((CancelStatement) stmt);
        if (stmtType == StatementTypeEnum.ACCEPT) return serializeAccept((AcceptStatement) stmt);
        if (stmtType == StatementTypeEnum.OPEN) return serializeOpen((OpenStatement) stmt);
        if (stmtType == StatementTypeEnum.CLOSE) return serializeClose((CloseStatement) stmt);
        if (stmtType == StatementTypeEnum.READ) return serializeRead((ReadStatement) stmt);
        if (stmtType == StatementTypeEnum.WRITE) return serializeWrite((WriteStatement) stmt);

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
            // Source operand: the value being multiplied (e.g., WS-A in MULTIPLY WS-A BY WS-RESULT)
            ValueStmt operandVs = stmt.getOperandValueStmt();
            if (operandVs != null) {
                operands.add(extractValueStmtText(operandVs));
            }

            // Target operand(s): the BY variable(s) that receive the result
            // MULTIPLY WS-A BY WS-RESULT => WS-RESULT = WS-RESULT * WS-A
            io.proleap.cobol.asg.metamodel.procedure.multiply.ByPhrase byPhrase = stmt.getByPhrase();
            if (byPhrase != null) {
                for (ByOperand byOp : byPhrase.getByOperands()) {
                    Call targetCall = byOp.getOperandCall();
                    if (targetCall != null) {
                        operands.add(extractCallName(targetCall));
                    }
                }
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
            // Source operand: the divisor (e.g., WS-B in DIVIDE WS-B INTO WS-RESULT)
            ValueStmt operandVs = stmt.getOperandValueStmt();
            if (operandVs != null) {
                operands.add(extractValueStmtText(operandVs));
            }

            // Target operand(s): the INTO variable(s) that receive the result
            // DIVIDE WS-B INTO WS-RESULT => WS-RESULT = WS-RESULT / WS-B
            DivideIntoStatement intoStmt = stmt.getDivideIntoStatement();
            if (intoStmt != null) {
                for (Into into : intoStmt.getIntos()) {
                    Call targetCall = into.getGivingCall();
                    if (targetCall != null) {
                        operands.add(extractCallName(targetCall));
                    }
                }
            }
        } catch (Exception e) {
            LOG.fine("Could not extract DIVIDE operands: " + e.getMessage());
        }
        obj.add("operands", operands);
        return obj;
    }

    private static JsonObject serializeCompute(ComputeStatement stmt) {
        JsonObject obj = newStatement("COMPUTE");

        // Extract arithmetic expression as original source text (spaces preserved)
        try {
            if (stmt.getArithmeticExpression() != null && stmt.getArithmeticExpression().getCtx() != null) {
                var ctx = stmt.getArithmeticExpression().getCtx();
                Token start = ctx.getStart();
                Token stop = ctx.getStop();
                if (start != null && stop != null) {
                    CharStream input = start.getInputStream();
                    String exprText = input.getText(
                            Interval.of(start.getStartIndex(), stop.getStopIndex()));
                    obj.addProperty("expression", exprText.trim());
                }
            }
        } catch (Exception e) {
            LOG.fine("Could not extract COMPUTE expression: " + e.getMessage());
        }

        // Extract target variables
        JsonArray targets = new JsonArray();
        for (Store store : stmt.getStores()) {
            Call storeCall = store.getStoreCall();
            if (storeCall != null) {
                targets.add(extractCallName(storeCall));
            }
        }

        if (targets.size() > 0) {
            obj.add("targets", targets);
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
        if (children.size() > 0) {
            obj.add("children", children);
        }

        JsonArray elseChildren = new JsonArray();
        Else elseBlock = stmt.getElse();
        if (elseBlock != null && elseBlock.getStatements() != null) {
            for (Statement elseStmt : elseBlock.getStatements()) {
                JsonObject child = serializeStatement(elseStmt);
                if (child != null) {
                    elseChildren.add(child);
                }
            }
        }
        if (elseChildren.size() > 0) {
            obj.add("else_children", elseChildren);
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

    private static JsonObject serializeContinue(ContinueStatement stmt) {
        return newStatement("CONTINUE");
    }

    private static JsonObject serializeExit(ExitStatement stmt) {
        return newStatement("EXIT");
    }

    private static JsonObject serializeInitialize(InitializeStatement stmt) {
        JsonObject obj = newStatement("INITIALIZE");
        JsonArray operands = new JsonArray();
        try {
            for (Call dataItemCall : stmt.getDataItemCalls()) {
                operands.add(extractCallName(dataItemCall));
            }
        } catch (Exception e) {
            LOG.fine("Could not extract INITIALIZE operands: " + e.getMessage());
        }
        obj.add("operands", operands);
        return obj;
    }

    private static JsonObject serializeSet(SetStatement stmt) {
        JsonObject obj = newStatement("SET");
        try {
            SetStatement.SetType setType = stmt.getSetType();
            if (setType == SetStatement.SetType.TO) {
                obj.addProperty("set_type", "TO");
                JsonArray targets = new JsonArray();
                JsonArray values = new JsonArray();
                for (SetTo setTo : stmt.getSetTos()) {
                    for (io.proleap.cobol.asg.metamodel.procedure.set.To to : setTo.getTos()) {
                        targets.add(extractCallName(to.getToCall()));
                    }
                    for (io.proleap.cobol.asg.metamodel.procedure.set.Value val : setTo.getValues()) {
                        values.add(extractValueStmtText(val.getValueStmt()));
                    }
                }
                obj.add("targets", targets);
                obj.add("values", values);
            } else if (setType == SetStatement.SetType.BY) {
                obj.addProperty("set_type", "BY");
                SetBy setBy = stmt.getSetBy();
                if (setBy != null) {
                    String byType = (setBy.getSetByType() == SetBy.SetByType.UP) ? "UP" : "DOWN";
                    obj.addProperty("by_type", byType);
                    JsonArray targets = new JsonArray();
                    for (io.proleap.cobol.asg.metamodel.procedure.set.To to : setBy.getTos()) {
                        targets.add(extractCallName(to.getToCall()));
                    }
                    obj.add("targets", targets);
                    if (setBy.getBy() != null && setBy.getBy().getByValueStmt() != null) {
                        obj.addProperty("value", extractValueStmtText(setBy.getBy().getByValueStmt()));
                    }
                }
            }
        } catch (Exception e) {
            LOG.fine("Could not extract SET operands: " + e.getMessage());
        }
        return obj;
    }

    private static JsonObject serializeString(StringStatement stmt) {
        JsonObject obj = newStatement("STRING");
        try {
            JsonArray sendings = new JsonArray();
            for (Sendings sending : stmt.getSendings()) {
                JsonObject sendingObj = new JsonObject();
                List<ValueStmt> valueStmts = sending.getSendingValueStmts();
                if (!valueStmts.isEmpty()) {
                    sendingObj.addProperty("value", extractValueStmtText(valueStmts.get(0)));
                }
                DelimitedByPhrase dbp = sending.getDelimitedByPhrase();
                if (dbp != null) {
                    DelimitedByPhrase.DelimitedByType dbType = dbp.getDelimitedByType();
                    if (dbType == DelimitedByPhrase.DelimitedByType.SIZE) {
                        sendingObj.addProperty("delimited_by", "SIZE");
                    } else if (dbp.getCharactersValueStmt() != null) {
                        sendingObj.addProperty("delimited_by",
                                extractValueStmtText(dbp.getCharactersValueStmt()));
                    }
                }
                sendings.add(sendingObj);
            }
            obj.add("sendings", sendings);
            if (stmt.getIntoPhrase() != null && stmt.getIntoPhrase().getIntoCall() != null) {
                obj.addProperty("into", extractCallName(stmt.getIntoPhrase().getIntoCall()));
            }
        } catch (Exception e) {
            LOG.fine("Could not extract STRING operands: " + e.getMessage());
        }
        return obj;
    }

    private static JsonObject serializeUnstring(UnstringStatement stmt) {
        JsonObject obj = newStatement("UNSTRING");
        try {
            if (stmt.getSending() != null && stmt.getSending().getSendingCall() != null) {
                obj.addProperty("source", extractCallName(stmt.getSending().getSendingCall()));
            }
            // Delimiter
            if (stmt.getSending() != null && stmt.getSending().getDelimitedByPhrase() != null) {
                ValueStmt delimVs = stmt.getSending().getDelimitedByPhrase().getDelimitedByValueStmt();
                if (delimVs != null) {
                    obj.addProperty("delimited_by", extractValueStmtText(delimVs));
                }
            }
            // INTO targets
            if (stmt.getIntoPhrase() != null) {
                JsonArray intoArr = new JsonArray();
                for (io.proleap.cobol.asg.metamodel.procedure.unstring.Into into : stmt.getIntoPhrase().getIntos()) {
                    if (into.getIntoCall() != null) {
                        intoArr.add(extractCallName(into.getIntoCall()));
                    }
                }
                obj.add("into", intoArr);
            }
        } catch (Exception e) {
            LOG.fine("Could not extract UNSTRING operands: " + e.getMessage());
        }
        return obj;
    }

    private static JsonObject serializeInspect(InspectStatement stmt) {
        JsonObject obj = newStatement("INSPECT");
        try {
            if (stmt.getDataItemCall() != null) {
                obj.addProperty("source", extractCallName(stmt.getDataItemCall()));
            }
            InspectStatement.InspectType inspType = stmt.getInspectType();
            if (inspType == InspectStatement.InspectType.TALLYING) {
                obj.addProperty("inspect_type", "TALLYING");
                if (stmt.getTallying() != null) {
                    JsonArray tallyingFor = new JsonArray();
                    for (io.proleap.cobol.asg.metamodel.procedure.inspect.For forItem : stmt.getTallying().getFors()) {
                        if (forItem.getTallyCountDataItemCall() != null) {
                            obj.addProperty("tallying_target",
                                    extractCallName(forItem.getTallyCountDataItemCall()));
                        }
                        for (AllLeadingPhrase alp : forItem.getAllLeadingPhrase()) {
                            String mode = (alp.getAllLeadingsType() == AllLeadingPhrase.AllLeadingsType.ALL) ? "ALL" : "LEADING";
                            for (AllLeading al : alp.getAllLeadings()) {
                                JsonObject forObj = new JsonObject();
                                forObj.addProperty("mode", mode);
                                if (al.getPatternDataItemValueStmt() != null) {
                                    forObj.addProperty("pattern",
                                            extractValueStmtText(al.getPatternDataItemValueStmt()));
                                }
                                tallyingFor.add(forObj);
                            }
                        }
                    }
                    obj.add("tallying_for", tallyingFor);
                }
            } else if (inspType == InspectStatement.InspectType.REPLACING) {
                obj.addProperty("inspect_type", "REPLACING");
                if (stmt.getReplacing() != null) {
                    JsonArray replacings = new JsonArray();
                    for (ReplacingAllLeadings rals : stmt.getReplacing().getAllLeadings()) {
                        String mode;
                        switch (rals.getReplacingAllLeadingsType()) {
                            case ALL: mode = "ALL"; break;
                            case FIRST: mode = "FIRST"; break;
                            case LEADING: mode = "LEADING"; break;
                            default: mode = "ALL"; break;
                        }
                        for (ReplacingAllLeading ral : rals.getAllLeadings()) {
                            JsonObject repObj = new JsonObject();
                            repObj.addProperty("mode", mode);
                            if (ral.getPatternDataItemValueStmt() != null) {
                                repObj.addProperty("from",
                                        extractValueStmtText(ral.getPatternDataItemValueStmt()));
                            }
                            if (ral.getBy() != null && ral.getBy().getByValueStmt() != null) {
                                repObj.addProperty("to",
                                        extractValueStmtText(ral.getBy().getByValueStmt()));
                            }
                            replacings.add(repObj);
                        }
                    }
                    obj.add("replacings", replacings);
                }
            }
        } catch (Exception e) {
            LOG.fine("Could not extract INSPECT operands: " + e.getMessage());
        }
        return obj;
    }

    private static JsonObject serializeSearch(SearchStatement stmt) {
        JsonObject obj = newStatement("SEARCH");
        try {
            // Table being searched
            if (stmt.getDataCall() != null) {
                obj.addProperty("table", extractCallName(stmt.getDataCall()));
            }

            // VARYING index variable (optional)
            if (stmt.getVaryingPhrase() != null && stmt.getVaryingPhrase().getDataCall() != null) {
                obj.addProperty("varying", extractCallName(stmt.getVaryingPhrase().getDataCall()));
            }

            // WHEN clauses
            JsonArray whens = new JsonArray();
            for (io.proleap.cobol.asg.metamodel.procedure.search.WhenPhrase when : stmt.getWhenPhrases()) {
                JsonObject whenObj = new JsonObject();
                // Extract condition text
                if (when.getCondition() != null && when.getCondition().getCtx() != null) {
                    whenObj.addProperty("condition", insertSpaces(when.getCondition().getCtx().getText()));
                }
                // Serialize child statements
                if (when.getStatements() != null && !when.getStatements().isEmpty()) {
                    JsonArray children = serializeStatements(when.getStatements());
                    if (children.size() > 0) {
                        whenObj.add("children", children);
                    }
                }
                whens.add(whenObj);
            }
            obj.add("whens", whens);

            // AT END clause
            if (stmt.getAtEndPhrase() != null && stmt.getAtEndPhrase().getStatements() != null) {
                JsonArray atEndChildren = serializeStatements(stmt.getAtEndPhrase().getStatements());
                if (atEndChildren.size() > 0) {
                    obj.add("at_end", atEndChildren);
                }
            }
        } catch (Exception e) {
            LOG.fine("Could not extract SEARCH operands: " + e.getMessage());
        }
        return obj;
    }

    private static JsonObject serializeCall(CallStatement stmt) {
        JsonObject obj = newStatement("CALL");
        try {
            // Program name
            if (stmt.getProgramValueStmt() != null) {
                String progName = extractValueStmtText(stmt.getProgramValueStmt());
                // Strip quotes from literal program names (e.g., 'SUBPROG' -> SUBPROG)
                progName = progName.replaceAll("^['\"]|['\"]$", "");
                obj.addProperty("program", progName);
            }
            // USING parameters
            if (stmt.getUsingPhrase() != null && stmt.getUsingPhrase().getUsingParameters() != null) {
                JsonArray params = new JsonArray();
                for (UsingParameter param : stmt.getUsingPhrase().getUsingParameters()) {
                    JsonObject paramObj = new JsonObject();
                    String paramType = "REFERENCE"; // default
                    if (param.getParameterType() != null) {
                        paramType = param.getParameterType().name();
                    }
                    paramObj.addProperty("type", paramType);
                    // Extract the actual operand name from the appropriate phrase
                    String paramName = "";
                    if (param.getByReferencePhrase() != null && param.getByReferencePhrase().getByReferences() != null
                            && !param.getByReferencePhrase().getByReferences().isEmpty()) {
                        ValueStmt vs = param.getByReferencePhrase().getByReferences().get(0).getValueStmt();
                        paramName = extractValueStmtText(vs);
                    } else if (param.getByContentPhrase() != null && param.getByContentPhrase().getByContents() != null
                            && !param.getByContentPhrase().getByContents().isEmpty()) {
                        ValueStmt vs = param.getByContentPhrase().getByContents().get(0).getValueStmt();
                        paramName = extractValueStmtText(vs);
                    } else if (param.getByValuePhrase() != null && param.getByValuePhrase().getByValues() != null
                            && !param.getByValuePhrase().getByValues().isEmpty()) {
                        ValueStmt vs = param.getByValuePhrase().getByValues().get(0).getValueStmt();
                        paramName = extractValueStmtText(vs);
                    }
                    paramObj.addProperty("name", paramName);
                    params.add(paramObj);
                }
                obj.add("using", params);
            }
            // GIVING
            if (stmt.getGivingPhrase() != null && stmt.getGivingPhrase().getGivingCall() != null) {
                obj.addProperty("giving", extractCallName(stmt.getGivingPhrase().getGivingCall()));
            }
        } catch (Exception e) {
            LOG.fine("Could not extract CALL operands: " + e.getMessage());
        }
        return obj;
    }

    private static JsonObject serializeAlter(AlterStatement stmt) {
        JsonObject obj = newStatement("ALTER");
        try {
            if (stmt.getProceedTos() != null) {
                JsonArray proceeds = new JsonArray();
                for (ProceedTo pt : stmt.getProceedTos()) {
                    JsonObject ptObj = new JsonObject();
                    if (pt.getSourceCall() != null) {
                        ptObj.addProperty("source", extractCallName(pt.getSourceCall()));
                    }
                    if (pt.getTargetCall() != null) {
                        ptObj.addProperty("target", extractCallName(pt.getTargetCall()));
                    }
                    proceeds.add(ptObj);
                }
                obj.add("proceed_tos", proceeds);
            }
        } catch (Exception e) {
            LOG.fine("Could not extract ALTER operands: " + e.getMessage());
        }
        return obj;
    }

    private static JsonObject serializeEntry(EntryStatement stmt) {
        JsonObject obj = newStatement("ENTRY");
        try {
            if (stmt.getEntryValueStmt() != null) {
                String entryName = extractValueStmtText(stmt.getEntryValueStmt());
                entryName = entryName.replaceAll("^['\"]|['\"]$", "");
                obj.addProperty("entry_name", entryName);
            }
            if (stmt.getUsingCalls() != null && !stmt.getUsingCalls().isEmpty()) {
                JsonArray usingArr = new JsonArray();
                for (Call call : stmt.getUsingCalls()) {
                    usingArr.add(extractCallName(call));
                }
                obj.add("using", usingArr);
            }
        } catch (Exception e) {
            LOG.fine("Could not extract ENTRY operands: " + e.getMessage());
        }
        return obj;
    }

    private static JsonObject serializeCancel(CancelStatement stmt) {
        JsonObject obj = newStatement("CANCEL");
        try {
            if (stmt.getCancelCalls() != null) {
                JsonArray programs = new JsonArray();
                for (io.proleap.cobol.asg.metamodel.procedure.cancel.CancelCall cc : stmt.getCancelCalls()) {
                    if (cc.getValueStmt() != null) {
                        String name = extractValueStmtText(cc.getValueStmt());
                        name = name.replaceAll("^['\"]|['\"]$", "");
                        programs.add(name);
                    }
                }
                obj.add("programs", programs);
            }
        } catch (Exception e) {
            LOG.fine("Could not extract CANCEL operands: " + e.getMessage());
        }
        return obj;
    }

    private static JsonObject serializeAccept(AcceptStatement stmt) {
        JsonObject obj = newStatement("ACCEPT");
        try {
            if (stmt.getAcceptCall() != null) {
                obj.addProperty("target", extractCallName(stmt.getAcceptCall()));
            }
            // FROM device — AcceptStatement.AcceptType distinguishes
            // DATE/DAY/TIME vs. environment name vs. mnemonic.
            // For simplicity, default to CONSOLE (user input).
            if (stmt.getAcceptType() != null) {
                obj.addProperty("from_device", stmt.getAcceptType().name());
            }
        } catch (Exception e) {
            LOG.fine("Could not extract ACCEPT operands: " + e.getMessage());
        }
        return obj;
    }

    private static JsonObject serializeOpen(OpenStatement stmt) {
        JsonObject obj = newStatement("OPEN");
        try {
            JsonArray files = new JsonArray();
            String mode = "";

            // INPUT files
            List<io.proleap.cobol.asg.metamodel.procedure.open.InputPhrase> inputPhrases = stmt.getInputPhrases();
            if (inputPhrases != null && !inputPhrases.isEmpty()) {
                mode = "INPUT";
                inputPhrases.stream()
                    .flatMap(ip -> ip.getInputs().stream())
                    .map(io.proleap.cobol.asg.metamodel.procedure.open.Input::getFileCall)
                    .filter(c -> c != null)
                    .map(StatementSerializer::extractCallName)
                    .forEach(files::add);
            }

            // OUTPUT files
            List<io.proleap.cobol.asg.metamodel.procedure.open.OutputPhrase> outputPhrases = stmt.getOutputPhrases();
            if (outputPhrases != null && !outputPhrases.isEmpty()) {
                mode = "OUTPUT";
                outputPhrases.stream()
                    .flatMap(op -> op.getOutputs().stream())
                    .map(io.proleap.cobol.asg.metamodel.procedure.open.Output::getFileCall)
                    .filter(c -> c != null)
                    .map(StatementSerializer::extractCallName)
                    .forEach(files::add);
            }

            // I-O files
            List<io.proleap.cobol.asg.metamodel.procedure.open.InputOutputPhrase> ioPhrases = stmt.getInputOutputPhrases();
            if (ioPhrases != null && !ioPhrases.isEmpty()) {
                mode = "I-O";
                ioPhrases.stream()
                    .flatMap(iop -> iop.getFileCalls().stream())
                    .map(StatementSerializer::extractCallName)
                    .forEach(files::add);
            }

            // EXTEND files
            List<io.proleap.cobol.asg.metamodel.procedure.open.ExtendPhrase> extendPhrases = stmt.getExtendPhrases();
            if (extendPhrases != null && !extendPhrases.isEmpty()) {
                mode = "EXTEND";
                extendPhrases.stream()
                    .flatMap(ep -> ep.getFileCalls().stream())
                    .map(StatementSerializer::extractCallName)
                    .forEach(files::add);
            }

            obj.addProperty("mode", mode);
            obj.add("files", files);
        } catch (Exception e) {
            LOG.fine("Could not extract OPEN operands: " + e.getMessage());
        }
        return obj;
    }

    private static JsonObject serializeClose(CloseStatement stmt) {
        JsonObject obj = newStatement("CLOSE");
        try {
            JsonArray files = new JsonArray();
            if (stmt.getCloseFiles() != null) {
                stmt.getCloseFiles().stream()
                    .map(io.proleap.cobol.asg.metamodel.procedure.close.CloseFile::getFileCall)
                    .filter(c -> c != null)
                    .map(StatementSerializer::extractCallName)
                    .forEach(files::add);
            }
            obj.add("files", files);
        } catch (Exception e) {
            LOG.fine("Could not extract CLOSE operands: " + e.getMessage());
        }
        return obj;
    }

    private static JsonObject serializeRead(ReadStatement stmt) {
        JsonObject obj = newStatement("READ");
        try {
            if (stmt.getFileCall() != null) {
                obj.addProperty("file_name", extractCallName(stmt.getFileCall()));
            }
            io.proleap.cobol.asg.metamodel.procedure.read.Into into = stmt.getInto();
            if (into != null && into.getIntoCall() != null) {
                obj.addProperty("into", extractCallName(into.getIntoCall()));
            }
        } catch (Exception e) {
            LOG.fine("Could not extract READ operands: " + e.getMessage());
        }
        return obj;
    }

    private static JsonObject serializeWrite(WriteStatement stmt) {
        JsonObject obj = newStatement("WRITE");
        try {
            if (stmt.getRecordCall() != null) {
                obj.addProperty("record_name", extractCallName(stmt.getRecordCall()));
            }
            io.proleap.cobol.asg.metamodel.procedure.write.From from = stmt.getFrom();
            if (from != null && from.getFromValueStmt() != null) {
                obj.addProperty("from_field", extractValueStmtText(from.getFromValueStmt()));
            }
        } catch (Exception e) {
            LOG.fine("Could not extract WRITE operands: " + e.getMessage());
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
