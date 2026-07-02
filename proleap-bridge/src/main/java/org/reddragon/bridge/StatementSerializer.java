package org.reddragon.bridge;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonPrimitive;
import io.proleap.cobol.asg.metamodel.procedure.Statement;
import io.proleap.cobol.asg.metamodel.procedure.StatementType;
import io.proleap.cobol.asg.metamodel.procedure.StatementTypeEnum;
import io.proleap.cobol.asg.metamodel.procedure.add.AddStatement;
import io.proleap.cobol.asg.metamodel.procedure.add.AddToGivingStatement;
import io.proleap.cobol.asg.metamodel.procedure.add.AddToStatement;
import io.proleap.cobol.asg.metamodel.procedure.add.From;
import io.proleap.cobol.asg.metamodel.procedure.add.To;
import io.proleap.cobol.asg.metamodel.procedure.add.ToGiving;
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
import io.proleap.cobol.asg.metamodel.procedure.divide.Remainder;
import io.proleap.cobol.asg.metamodel.procedure.evaluate.AlsoCondition;
import io.proleap.cobol.asg.metamodel.procedure.evaluate.AlsoSelect;
import io.proleap.cobol.asg.metamodel.procedure.evaluate.EvaluateStatement;
import io.proleap.cobol.asg.metamodel.procedure.evaluate.WhenPhrase;
import io.proleap.cobol.asg.metamodel.procedure.exit.ExitStatement;
import io.proleap.cobol.asg.metamodel.procedure.gotostmt.GoToStatement;
import io.proleap.cobol.asg.metamodel.procedure.gotostmt.DependingOnPhrase;
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
import io.proleap.cobol.asg.metamodel.procedure.goback.GobackStatement;
import io.proleap.cobol.asg.metamodel.procedure.call.ByContent;
import io.proleap.cobol.asg.metamodel.procedure.call.ByReference;
import io.proleap.cobol.asg.metamodel.procedure.call.ByValue;
import io.proleap.cobol.asg.metamodel.procedure.call.CallStatement;
import io.proleap.cobol.asg.metamodel.procedure.call.UsingParameter;
import io.proleap.cobol.asg.metamodel.procedure.accept.AcceptStatement;
import io.proleap.cobol.asg.metamodel.procedure.cancel.CancelStatement;
import io.proleap.cobol.asg.metamodel.procedure.close.CloseStatement;
import io.proleap.cobol.asg.metamodel.procedure.entry.EntryStatement;
import io.proleap.cobol.asg.metamodel.procedure.move.MoveStatement;
import io.proleap.cobol.asg.metamodel.procedure.move.MoveStatement.MoveType;
import io.proleap.cobol.asg.metamodel.procedure.move.MoveToStatement;
import io.proleap.cobol.asg.metamodel.procedure.move.MoveToSendingArea;
import io.proleap.cobol.asg.metamodel.procedure.move.MoveCorrespondingToStatetement;
import io.proleap.cobol.asg.metamodel.procedure.move.MoveCorrespondingToSendingArea;
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
import io.proleap.cobol.asg.metamodel.procedure.perform.After;
import io.proleap.cobol.asg.metamodel.procedure.perform.VaryingPhrase;
import io.proleap.cobol.asg.metamodel.procedure.set.SetBy;
import io.proleap.cobol.asg.metamodel.procedure.set.SetStatement;
import io.proleap.cobol.asg.metamodel.procedure.set.SetTo;
import io.proleap.cobol.asg.metamodel.procedure.stop.StopStatement;
import io.proleap.cobol.asg.metamodel.procedure.string.DelimitedByPhrase;
import io.proleap.cobol.asg.metamodel.procedure.string.Sendings;
import io.proleap.cobol.asg.metamodel.procedure.string.StringStatement;
import io.proleap.cobol.asg.metamodel.procedure.subtract.MinuendGiving;
import io.proleap.cobol.asg.metamodel.procedure.subtract.SubtractStatement;
import io.proleap.cobol.asg.metamodel.procedure.subtract.SubtractFromStatement;
import io.proleap.cobol.asg.metamodel.procedure.subtract.SubtractFromGivingStatement;
import io.proleap.cobol.asg.metamodel.procedure.subtract.Minuend;
import io.proleap.cobol.asg.metamodel.procedure.subtract.Subtrahend;
import io.proleap.cobol.asg.metamodel.procedure.unstring.UnstringStatement;
import io.proleap.cobol.asg.metamodel.procedure.write.WriteStatement;
import io.proleap.cobol.asg.metamodel.procedure.delete.DeleteStatement;
import io.proleap.cobol.asg.metamodel.procedure.rewrite.RewriteStatement;
import io.proleap.cobol.asg.metamodel.procedure.start.StartStatement;
import io.proleap.cobol.asg.metamodel.procedure.execcics.ExecCicsStatement;
import io.proleap.cobol.asg.metamodel.procedure.execsql.ExecSqlStatement;
import io.proleap.cobol.asg.metamodel.call.Call;
import io.proleap.cobol.asg.metamodel.call.TableCall;
import io.proleap.cobol.asg.metamodel.valuestmt.ArithmeticValueStmt;
import io.proleap.cobol.asg.metamodel.valuestmt.CallValueStmt;
import io.proleap.cobol.asg.metamodel.valuestmt.ConditionValueStmt;
import io.proleap.cobol.asg.metamodel.valuestmt.RelationConditionValueStmt;
import io.proleap.cobol.asg.metamodel.valuestmt.Subscript;
import io.proleap.cobol.asg.metamodel.valuestmt.ValueStmt;
import io.proleap.cobol.asg.metamodel.valuestmt.arithmetic.Basis;
import io.proleap.cobol.asg.metamodel.valuestmt.arithmetic.MultDiv;
import io.proleap.cobol.asg.metamodel.valuestmt.arithmetic.MultDivs;
import io.proleap.cobol.asg.metamodel.valuestmt.arithmetic.PlusMinus;
import io.proleap.cobol.asg.metamodel.valuestmt.arithmetic.Powers;
import io.proleap.cobol.asg.metamodel.valuestmt.condition.AndOrCondition;
import io.proleap.cobol.asg.metamodel.valuestmt.condition.CombinableCondition;
import io.proleap.cobol.asg.metamodel.valuestmt.condition.ClassCondition;
import io.proleap.cobol.asg.metamodel.valuestmt.condition.ConditionNameReference;
import io.proleap.cobol.asg.metamodel.valuestmt.condition.SimpleCondition;
import io.proleap.cobol.asg.metamodel.valuestmt.LiteralValueStmt;
import io.proleap.cobol.asg.metamodel.Literal;
import io.proleap.cobol.asg.metamodel.FigurativeConstant;
import io.proleap.cobol.asg.metamodel.valuestmt.relation.ArithmeticComparison;
import io.proleap.cobol.asg.metamodel.valuestmt.relation.CombinedComparison;
import io.proleap.cobol.asg.metamodel.valuestmt.relation.CombinedCondition;
import io.proleap.cobol.asg.metamodel.valuestmt.relation.RelationalOperator;
import io.proleap.cobol.asg.metamodel.valuestmt.relation.SignCondition;

import io.proleap.cobol.asg.metamodel.impl.ASGElementImpl;
import io.proleap.cobol.CobolParser;
import org.antlr.v4.runtime.ParserRuleContext;

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
        if (stmtType == StatementTypeEnum.GO_BACK) return serializeGoback((GobackStatement) stmt);
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
        if (stmtType == StatementTypeEnum.REWRITE) return serializeRewrite((RewriteStatement) stmt);
        if (stmtType == StatementTypeEnum.START) return serializeStart((StartStatement) stmt);
        if (stmtType == StatementTypeEnum.DELETE) return serializeDelete((DeleteStatement) stmt);
        if (stmtType == StatementTypeEnum.EXEC_CICS) return serializeExecCics((ExecCicsStatement) stmt);
        if (stmtType == StatementTypeEnum.EXEC_SQL) return serializeExecSql((ExecSqlStatement) stmt);

        return serializeUnknown(stmtType);
    }

    private static JsonObject serializeMove(MoveStatement stmt) {
        // Handle MOVE CORRESPONDING separately
        if (stmt.getMoveType() == MoveType.MOVE_CORRESPONDING) {
            JsonObject obj = newStatement("MOVE_CORRESPONDING");
            MoveCorrespondingToStatetement corr = stmt.getMoveCorrespondingToStatement();
            if (corr != null) {
                MoveCorrespondingToSendingArea sendingArea = corr.getMoveToCorrespondingSendingArea();
                if (sendingArea != null) {
                    Call sourceCall = sendingArea.getSendingAreaCall();
                    if (sourceCall != null) {
                        obj.addProperty("source", extractCallName(sourceCall));
                    }
                }
                JsonArray targets = new JsonArray();
                for (Call receivingCall : corr.getReceivingAreaCalls()) {
                    targets.add(extractCallName(receivingCall));
                }
                obj.add("targets", targets);
            }
            return obj;
        }

        // Handle MOVE TO — operands are now objects {name, ref_mod_start?, ref_mod_length?}
        JsonObject obj = newStatement("MOVE");
        JsonArray operands = new JsonArray();

        MoveToStatement moveToStmt = stmt.getMoveToStatement();
        if (moveToStmt != null) {
            MoveToSendingArea sendingArea = moveToStmt.getSendingArea();
            if (sendingArea != null) {
                ValueStmt vs = sendingArea.getSendingAreaValueStmt();
                Call sourceCall = null;
                if (vs instanceof CallValueStmt) {
                    sourceCall = ((CallValueStmt) vs).getCall();
                }
                JsonObject functionNode =
                        (sourceCall != null) ? serializeFunctionNode(sourceCall) : null;
                if (functionNode == null) {
                    // ValueStmt's own ctx may carry the functionCall even when the
                    // Call does not (e.g. CURRENT-DATE with no parenthesised args).
                    functionNode = serializeFunctionNodeFromValueStmt(vs);
                }
                JsonObject lengthOfNode = serializeMoveLengthOfSource(vs);
                if (functionNode != null) {
                    operands.add(functionNode);
                } else if (lengthOfNode != null) {
                    // `MOVE LENGTH OF <field> TO ...` — emit a structured
                    // length_of node (the field's byte length) rather than a
                    // null-name literal. Mirrors serializeFromValue's handling
                    // (used by PERFORM VARYING FROM). (red-dragon)
                    operands.add(lengthOfNode);
                } else if (sourceCall != null) {
                    operands.add(serializeMoveOperand(sourceCall));
                } else if (vs instanceof LiteralValueStmt) {
                    JsonObject dfh = serializeDfhrespLit((LiteralValueStmt) vs);
                    if (dfh != null) {
                        operands.add(dfh);
                    } else {
                        JsonObject srcObj = new JsonObject();
                        srcObj.addProperty("name", extractValueStmtText(vs));
                        operands.add(srcObj);
                    }
                } else {
                    // Complex expression source: plain name object, no ref mod
                    JsonObject srcObj = new JsonObject();
                    srcObj.addProperty("name", extractValueStmtText(vs));
                    operands.add(srcObj);
                }
            }

            for (Call receivingCall : moveToStmt.getReceivingAreaCalls()) {
                operands.add(serializeMoveOperand(receivingCall));
            }
        }

        obj.add("operands", operands);
        return obj;
    }

    private static JsonObject serializeAdd(AddStatement stmt) {
        // ADD CORRESPONDING src TO dst
        io.proleap.cobol.asg.metamodel.procedure.add.AddCorrespondingStatement addCorr =
            stmt.getAddCorrespondingStatement();
        if (addCorr != null) {
            JsonObject obj = newStatement("ADD_CORRESPONDING");
            obj.addProperty("source", extractCallName(addCorr.getFromCall()));
            io.proleap.cobol.asg.metamodel.procedure.add.To corrTo = addCorr.getTo();
            if (corrTo != null) {
                obj.addProperty("target", extractCallName(corrTo.getToCall()));
            }
            return obj;
        }

        JsonObject obj = newStatement("ADD");
        JsonArray operands = new JsonArray();

        AddToStatement addTo = stmt.getAddToStatement();
        if (addTo != null) {
            for (From from : addTo.getFroms()) {
                ValueStmt vs = from.getFromValueStmt();
                operands.add(serializeArithSource(vs));
            }
            for (To to : addTo.getTos()) {
                JsonObject t = serializeRef(to.getToCall());
                t.addProperty("rounded", to.isRounded());
                operands.add(t);
            }
        } else {
            AddToGivingStatement addGiving = stmt.getAddToGivingStatement();
            if (addGiving != null) {
                for (From from : addGiving.getFroms()) {
                    operands.add(serializeArithSource(from.getFromValueStmt()));
                }
                for (ToGiving to : addGiving.getTos()) {
                    operands.add(extractValueStmtText(to.getToValueStmt()));
                }
                JsonArray givingTargets = new JsonArray();
                for (io.proleap.cobol.asg.metamodel.procedure.add.Giving g : addGiving.getGivings()) {
                    JsonObject gt = serializeRef(g.getGivingCall());
                    gt.addProperty("rounded", g.isRounded());
                    givingTargets.add(gt);
                }
                if (givingTargets.size() > 0) {
                    obj.add("giving", givingTargets);
                }
            }
        }

        obj.add("operands", operands);
        if (stmt.getOnSizeErrorPhrase() != null) {
            obj.add("on_size_error", serializeStatements(stmt.getOnSizeErrorPhrase().getStatements()));
        }
        if (stmt.getNotOnSizeErrorPhrase() != null) {
            obj.add("not_on_size_error", serializeStatements(stmt.getNotOnSizeErrorPhrase().getStatements()));
        }
        return obj;
    }

    private static JsonObject serializeSubtract(SubtractStatement stmt) {
        // SUBTRACT CORRESPONDING src FROM dst
        io.proleap.cobol.asg.metamodel.procedure.subtract.SubtractCorrespondingStatement subCorr =
            stmt.getSubtractCorrespondingStatement();
        if (subCorr != null) {
            JsonObject obj = newStatement("SUBTRACT_CORRESPONDING");
            obj.addProperty("source", extractCallName(subCorr.getSubtrahendCall()));
            io.proleap.cobol.asg.metamodel.procedure.subtract.MinuendCorresponding minCorr =
                subCorr.getMinuend();
            if (minCorr != null) {
                obj.addProperty("target", extractCallName(minCorr.getMinuendCall()));
            }
            return obj;
        }

        JsonObject obj = newStatement("SUBTRACT");
        JsonArray operands = new JsonArray();

        SubtractFromStatement subtractFrom = stmt.getSubtractFromStatement();
        if (subtractFrom != null) {
            for (Subtrahend sub : subtractFrom.getSubtrahends()) {
                ValueStmt vs = sub.getSubtrahendValueStmt();
                operands.add(serializeArithSource(vs));
            }
            for (Minuend min : subtractFrom.getMinuends()) {
                JsonObject t = serializeRef(min.getMinuendCall());
                t.addProperty("rounded", min.isRounded());
                operands.add(t);
            }
        } else {
            SubtractFromGivingStatement subtractGiving = stmt.getSubtractFromGivingStatement();
            if (subtractGiving != null) {
                // Minuend first (source), subtrahends second (target)
                // SUBTRACT X FROM Y GIVING Z → operands=[Y, X], giving=[Z]
                // Python computes source - target = Y - X
                MinuendGiving minuend = subtractGiving.getMinuend();
                if (minuend != null) {
                    operands.add(serializeArithSource(minuend.getMinuendValueStmt()));
                }
                for (Subtrahend sub : subtractGiving.getSubtrahends()) {
                    operands.add(serializeArithSource(sub.getSubtrahendValueStmt()));
                }
                JsonArray givingTargets = new JsonArray();
                for (io.proleap.cobol.asg.metamodel.procedure.subtract.Giving g : subtractGiving.getGivings()) {
                    JsonObject gt = serializeRef(g.getGivingCall());
                    gt.addProperty("rounded", g.isRounded());
                    givingTargets.add(gt);
                }
                if (givingTargets.size() > 0) {
                    obj.add("giving", givingTargets);
                }
            }
        }

        obj.add("operands", operands);
        if (stmt.getOnSizeErrorPhrase() != null) {
            obj.add("on_size_error", serializeStatements(stmt.getOnSizeErrorPhrase().getStatements()));
        }
        if (stmt.getNotOnSizeErrorPhrase() != null) {
            obj.add("not_on_size_error", serializeStatements(stmt.getNotOnSizeErrorPhrase().getStatements()));
        }
        return obj;
    }

    private static JsonObject serializeMultiply(MultiplyStatement stmt) {
        JsonObject obj = newStatement("MULTIPLY");
        JsonArray operands = new JsonArray();
        try {
            // Source operand: the value being multiplied
            ValueStmt operandVs = stmt.getOperandValueStmt();
            if (operandVs != null) {
                operands.add(serializeArithSource(operandVs));
            }

            MultiplyStatement.MultiplyType multiplyType = stmt.getMultiplyType();

            if (multiplyType == MultiplyStatement.MultiplyType.BY_GIVING) {
                // MULTIPLY X BY Y GIVING Z
                // operand = X (source), giving_operand = Y, giving_result = Z
                io.proleap.cobol.asg.metamodel.procedure.multiply.GivingPhrase givingPhrase = stmt.getGivingPhrase();
                if (givingPhrase != null) {
                    io.proleap.cobol.asg.metamodel.procedure.multiply.GivingOperand givingOp = givingPhrase.getGivingOperand();
                    if (givingOp != null && givingOp.getOperandValueStmt() != null) {
                        operands.add(serializeArithSource(givingOp.getOperandValueStmt()));
                    }
                    // GIVING targets
                    JsonArray givingTargets = new JsonArray();
                    for (io.proleap.cobol.asg.metamodel.procedure.multiply.GivingResult gr : givingPhrase.getGivingResults()) {
                        Call resultCall = gr.getResultCall();
                        if (resultCall != null) {
                            JsonObject gt = serializeRef(resultCall);
                            gt.addProperty("rounded", gr.isRounded());
                            givingTargets.add(gt);
                        }
                    }
                    if (givingTargets.size() > 0) {
                        obj.add("giving", givingTargets);
                    }
                }
            } else {
                // MULTIPLY X BY Y (in-place: Y = Y * X)
                io.proleap.cobol.asg.metamodel.procedure.multiply.ByPhrase byPhrase = stmt.getByPhrase();
                if (byPhrase != null) {
                    for (ByOperand byOp : byPhrase.getByOperands()) {
                        Call targetCall = byOp.getOperandCall();
                        if (targetCall != null) {
                            JsonObject t = serializeRef(targetCall);
                            t.addProperty("rounded", byOp.isRounded());
                            operands.add(t);
                        }
                    }
                }
            }
        } catch (Exception e) {
            LOG.fine("Could not extract MULTIPLY operands: " + e.getMessage());
        }
        obj.add("operands", operands);
        if (stmt.getOnSizeErrorPhrase() != null) {
            obj.add("on_size_error", serializeStatements(stmt.getOnSizeErrorPhrase().getStatements()));
        }
        if (stmt.getNotOnSizeErrorPhrase() != null) {
            obj.add("not_on_size_error", serializeStatements(stmt.getNotOnSizeErrorPhrase().getStatements()));
        }
        return obj;
    }

    private static JsonObject serializeDivide(DivideStatement stmt) {
        JsonObject obj = newStatement("DIVIDE");
        JsonArray operands = new JsonArray();
        try {
            // Source operand (the divisor or dividend depending on form)
            ValueStmt operandVs = stmt.getOperandValueStmt();
            if (operandVs != null) {
                operands.add(serializeArithSource(operandVs));
            }

            Remainder remainder = stmt.getRemainder();
            if (remainder != null && remainder.getRemainderCall() != null) {
                obj.add("remainder", serializeRef(remainder.getRemainderCall()));
            }

            DivideStatement.DivideType divideType = stmt.getDivideType();

            if (divideType == DivideStatement.DivideType.INTO_GIVING) {
                // DIVIDE X INTO Y GIVING Z => Z = Y / X
                DivideIntoGivingStatement intoGiving = stmt.getDivideIntoGivingStatement();
                if (intoGiving != null) {
                    if (intoGiving.getIntoValueStmt() != null) {
                        operands.add(serializeArithSource(intoGiving.getIntoValueStmt()));
                    }
                    GivingPhrase gp = intoGiving.getGivingPhrase();
                    if (gp != null) {
                        JsonArray givingTargets = new JsonArray();
                        for (Giving g : gp.getGivings()) {
                            Call givingCall = g.getGivingCall();
                            if (givingCall != null) {
                                JsonObject gt = serializeRef(givingCall);
                                gt.addProperty("rounded", g.isRounded());
                                givingTargets.add(gt);
                            }
                        }
                        if (givingTargets.size() > 0) {
                            obj.add("giving", givingTargets);
                        }
                    }
                }
            } else if (divideType == DivideStatement.DivideType.BY_GIVING) {
                // DIVIDE X BY Y GIVING Z => Z = X / Y
                DivideByGivingStatement byGiving = stmt.getDivideByGivingStatement();
                if (byGiving != null) {
                    if (byGiving.getByValueStmt() != null) {
                        operands.add(serializeArithSource(byGiving.getByValueStmt()));
                    }
                    GivingPhrase gp = byGiving.getGivingPhrase();
                    if (gp != null) {
                        JsonArray givingTargets = new JsonArray();
                        for (Giving g : gp.getGivings()) {
                            Call givingCall = g.getGivingCall();
                            if (givingCall != null) {
                                JsonObject gt = serializeRef(givingCall);
                                gt.addProperty("rounded", g.isRounded());
                                givingTargets.add(gt);
                            }
                        }
                        if (givingTargets.size() > 0) {
                            obj.add("giving", givingTargets);
                        }
                    }
                }
            } else {
                // DIVIDE X INTO Y (in-place: Y = Y / X)
                DivideIntoStatement intoStmt = stmt.getDivideIntoStatement();
                if (intoStmt != null) {
                    for (Into into : intoStmt.getIntos()) {
                        Call targetCall = into.getGivingCall();
                        if (targetCall != null) {
                            JsonObject t = serializeRef(targetCall);
                            t.addProperty("rounded", into.isRounded());
                            operands.add(t);
                        }
                    }
                }
            }
        } catch (Exception e) {
            LOG.fine("Could not extract DIVIDE operands: " + e.getMessage());
        }
        obj.add("operands", operands);
        if (stmt.getOnSizeErrorPhrase() != null) {
            obj.add("on_size_error", serializeStatements(stmt.getOnSizeErrorPhrase().getStatements()));
        }
        if (stmt.getNotOnSizeErrorPhrase() != null) {
            obj.add("not_on_size_error", serializeStatements(stmt.getNotOnSizeErrorPhrase().getStatements()));
        }
        return obj;
    }

    private static JsonObject serializeCompute(ComputeStatement stmt) {
        JsonObject obj = newStatement("COMPUTE");

        // Extract arithmetic expression using structured AST
        if (stmt.getArithmeticExpression() != null) {
            obj.add("expression", serializeArithmeticExpr(stmt.getArithmeticExpression()));
        }

        // Extract target variables
        JsonArray targets = new JsonArray();
        for (Store store : stmt.getStores()) {
            Call storeCall = store.getStoreCall();
            if (storeCall != null) {
                JsonObject t = new JsonObject();
                t.addProperty("name", extractCallName(storeCall));
                t.addProperty("rounded", store.isRounded());
                targets.add(t);
            }
        }

        if (targets.size() > 0) {
            obj.add("targets", targets);
        }

        if (stmt.getOnSizeErrorPhrase() != null) {
            obj.add("on_size_error", serializeStatements(
                stmt.getOnSizeErrorPhrase().getStatements()));
        }
        if (stmt.getNotOnSizeErrorPhrase() != null) {
            obj.add("not_on_size_error", serializeStatements(
                stmt.getNotOnSizeErrorPhrase().getStatements()));
        }
        return obj;
    }

    private static JsonObject serializeIf(IfStatement stmt) {
        JsonObject obj = newStatement("IF");

        try {
            if (stmt.getCondition() != null) {
                obj.add("condition", serializeConditionNode(stmt.getCondition()));
            }
        } catch (Exception e) {
            LOG.fine("Could not extract IF condition: " + e.getMessage());
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
                            obj.add("varying_from", serializeFromValue(vp.getFrom().getFromValueStmt()));
                        }
                        if (vp.getBy() != null && vp.getBy().getByValueStmt() != null) {
                            obj.addProperty("varying_by", extractValueStmtText(vp.getBy().getByValueStmt()));
                        }
                        if (vp.getUntil() != null) {
                            serializeUntilFields(vp.getUntil(), obj);
                        }
                    }
                    List<After> afters = vc.getAfters();
                    if (afters != null && !afters.isEmpty()) {
                        JsonArray afterArr = new JsonArray();
                        for (After after : afters) {
                            if (after == null) continue;
                            VaryingPhrase ap = after.getVaryingPhrase();
                            if (ap == null) continue;
                            JsonObject aObj = new JsonObject();
                            if (ap.getVaryingValueStmt() != null) {
                                aObj.addProperty("varying_var",
                                    extractValueStmtText(ap.getVaryingValueStmt()));
                            }
                            if (ap.getFrom() != null && ap.getFrom().getFromValueStmt() != null) {
                                aObj.add("varying_from",
                                    serializeFromValue(ap.getFrom().getFromValueStmt()));
                            }
                            if (ap.getBy() != null && ap.getBy().getByValueStmt() != null) {
                                aObj.addProperty("varying_by",
                                    extractValueStmtText(ap.getBy().getByValueStmt()));
                            }
                            if (ap.getUntil() != null) {
                                serializeUntilFields(ap.getUntil(), aObj);
                            }
                            afterArr.add(aObj);
                        }
                        if (afterArr.size() > 0) {
                            obj.add("after_specs", afterArr);
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
        if (until.getCondition() != null) {
            try {
                obj.add("until", serializeConditionNode(until.getCondition()));
            } catch (Exception e) {
                LOG.fine("Could not serialize UNTIL condition: " + e.getMessage());
            }
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
            if (vs instanceof CallValueStmt) {
                operands.add(serializeMoveOperand(((CallValueStmt) vs).getCall()));
            } else {
                JsonObject literalObj = new JsonObject();
                literalObj.addProperty("name", extractValueStmtText(vs));
                operands.add(literalObj);
            }
        }

        obj.add("operands", operands);
        return obj;
    }

    private static JsonObject serializeStop(StopStatement stmt) {
        return newStatement("STOP_RUN");
    }

    private static JsonObject serializeGoTo(GoToStatement stmt) {
        JsonObject obj = newStatement("GOTO");
        try {
            if (stmt.getGoToType() == GoToStatement.GoToType.DEPENDING_ON) {
                obj.addProperty("form", "computed");
                DependingOnPhrase dep = stmt.getDependingOnPhrase();
                JsonArray targets = new JsonArray();
                for (Call c : dep.getProcedureCalls()) {
                    targets.add(serializeProcedureRef(c));
                }
                obj.add("targets", targets);
                obj.add("index", serializeRef(dep.getDependingOnCall()));
            } else if (stmt.getSimple() != null
                    && stmt.getSimple().getProcedureCall() != null) {
                obj.addProperty("form", "simple");
                obj.add("target", serializeProcedureRef(stmt.getSimple().getProcedureCall()));
            } else {
                obj.addProperty("form", "altered");
            }
        } catch (Exception e) {
            LOG.fine("Could not extract GOTO: " + e.getMessage());
            obj.addProperty("form", "altered");
        }
        return obj;
    }

    private static JsonObject serializeProcedureRef(Call call) {
        JsonObject obj = new JsonObject();
        obj.addProperty("paragraph", extractCallName(call));
        JsonArray quals = extractQualifiers(call);
        obj.addProperty("section", quals.size() > 0 ? quals.get(0).getAsString() : "");
        return obj;
    }

    private static JsonObject serializeEvaluate(EvaluateStatement stmt) {
        JsonObject obj = newStatement("EVALUATE");
        JsonArray children = new JsonArray();

        try {
            // Extract the EVALUATE subject (e.g., WS-A in EVALUATE WS-A)
            io.proleap.cobol.asg.metamodel.procedure.evaluate.Select select = stmt.getSelect();
            if (select != null && select.getSelectValueStmt() != null) {
                // For a qualified subject (e.g. CONFIRMI OF COTRN2AI) the flat
                // text glues to "CONFIRMIOFCOTRN2AI"; insertSpaces only spaces
                // operators, not OF/IN. Use the LEAF data name so the frontend
                // resolves the field (it is unique within its scope here). Falls
                // back to the spaced flat text for non-qualified subjects. (red-dragon)
                String subject = qualifiedSubjectLeaf(select.getSelectValueStmt());
                if (subject == null) {
                    subject = insertSpaces(extractValueStmtText(select.getSelectValueStmt()));
                }
                obj.addProperty("subject", subject);
            }

            // EVALUATE subject ALSO also_subject ... (multi-subject form)
            List<AlsoSelect> alsoSelects = stmt.getAlsoSelects();
            if (alsoSelects != null && !alsoSelects.isEmpty()) {
                JsonArray alsoSubjectsArr = new JsonArray();
                for (AlsoSelect alsoSelect : alsoSelects) {
                    io.proleap.cobol.asg.metamodel.procedure.evaluate.Select alsoSel = alsoSelect.getSelect();
                    if (alsoSel != null && alsoSel.getSelectValueStmt() != null) {
                        String alsoSubject = qualifiedSubjectLeaf(alsoSel.getSelectValueStmt());
                        if (alsoSubject == null) {
                            alsoSubject = insertSpaces(extractValueStmtText(alsoSel.getSelectValueStmt()));
                        }
                        alsoSubjectsArr.add(alsoSubject);
                    }
                }
                if (alsoSubjectsArr.size() > 0) obj.add("also_subjects", alsoSubjectsArr);
            }

            // Each WhenPhrase is "WHEN c1 [WHEN c2 ...] statements": one or more
            // stacked conditions sharing a single body. Emit ONE WHEN child per
            // stacked condition, each carrying the (shared) body, so a match on
            // ANY stacked value runs the body. Serializing only whens.get(0)
            // previously dropped every value after the first.
            for (WhenPhrase whenPhrase : stmt.getWhenPhrases()) {
                List<io.proleap.cobol.asg.metamodel.procedure.evaluate.When> whens = whenPhrase.getWhens();
                boolean hasBody = whenPhrase.getStatements() != null
                        && !whenPhrase.getStatements().isEmpty();

                if (whens == null || whens.isEmpty()) {
                    JsonObject whenObj = newStatement("WHEN");
                    if (hasBody) {
                        JsonArray whenStmts = serializeStatements(whenPhrase.getStatements());
                        if (whenStmts.size() > 0) whenObj.add("children", whenStmts);
                    }
                    children.add(whenObj);
                    continue;
                }

                for (io.proleap.cobol.asg.metamodel.procedure.evaluate.When when : whens) {
                    JsonObject whenObj = newStatement("WHEN");
                    io.proleap.cobol.asg.metamodel.procedure.evaluate.Condition cond = when.getCondition();
                    if (cond != null) {
                        io.proleap.cobol.asg.metamodel.procedure.evaluate.Condition.ConditionType ct = cond.getConditionType();
                        ValueStmt cvs = cond.getConditionValueStmt();
                        if (ct == io.proleap.cobol.asg.metamodel.procedure.evaluate.Condition.ConditionType.CONDITION
                                && cvs instanceof ConditionValueStmt) {
                            // Full conditional expression (e.g. EVALUATE TRUE WHEN A = SPACES OR ...):
                            // route through the SAME structured serializer the IF path uses so
                            // figurative / OF-qualified / abbreviated conditions lower correctly.
                            whenObj.add("condition", serializeConditionNode((ConditionValueStmt) cvs));
                        } else if (ct == io.proleap.cobol.asg.metamodel.procedure.evaluate.Condition.ConditionType.ANY) {
                            // WHEN ANY — leave condition absent (always-match handled downstream).
                            whenObj.addProperty("condition", "ANY");
                        } else if (cond.getValue() != null && cond.getValue().getValueStmt() != null) {
                            ValueStmt whenVs = cond.getValue().getValueStmt();
                            JsonObject dfh = serializeDfhrespFromVS(whenVs);
                            if (dfh != null) {
                                // WHEN DFHRESP(X) — emit structured node; Python lower_evaluate
                                // detects kind=dfhresp and builds the subject comparison.
                                whenObj.add("condition", dfh);
                            } else {
                                // WHEN <value> against an EVALUATE subject — keep the value as text;
                                // the Python side prefixes it with "subject = ".
                                whenObj.addProperty("condition",
                                        insertSpaces(extractValueStmtText(whenVs)));
                            }
                            // WHEN <value> THRU <value2> range — emit the upper bound separately.
                            if (cond.getThrough() != null && cond.getThrough().getValue() != null
                                    && cond.getThrough().getValue().getValueStmt() != null) {
                                whenObj.addProperty("condition_thru",
                                        insertSpaces(extractValueStmtText(
                                                cond.getThrough().getValue().getValueStmt())));
                            }
                        } else if (cvs != null) {
                            whenObj.addProperty("condition", insertSpaces(extractValueStmtText(cvs)));
                        } else if (cond.getCtx() != null) {
                            whenObj.addProperty("condition", insertSpaces(cond.getCtx().getText()));
                        }
                    }

                    // WHEN val ALSO val ... (multi-subject form per-when conditions)
                    List<AlsoCondition> alsoConditions = when.getAlsoConditions();
                    if (alsoConditions != null && !alsoConditions.isEmpty()) {
                        JsonArray alsoCondsArr = new JsonArray();
                        for (AlsoCondition alsoCond : alsoConditions) {
                            io.proleap.cobol.asg.metamodel.procedure.evaluate.Condition aCond = alsoCond.getCondition();
                            if (aCond != null) {
                                io.proleap.cobol.asg.metamodel.procedure.evaluate.Condition.ConditionType act = aCond.getConditionType();
                                ValueStmt acvs = aCond.getConditionValueStmt();
                                if (act == io.proleap.cobol.asg.metamodel.procedure.evaluate.Condition.ConditionType.CONDITION
                                        && acvs instanceof ConditionValueStmt) {
                                    alsoCondsArr.add(serializeConditionNode((ConditionValueStmt) acvs));
                                } else if (act == io.proleap.cobol.asg.metamodel.procedure.evaluate.Condition.ConditionType.ANY) {
                                    alsoCondsArr.add(new JsonPrimitive("ANY"));
                                } else if (aCond.getValue() != null && aCond.getValue().getValueStmt() != null) {
                                    ValueStmt alsoVs = aCond.getValue().getValueStmt();
                                    JsonObject dfhAlso = serializeDfhrespFromVS(alsoVs);
                                    if (dfhAlso != null) {
                                        alsoCondsArr.add(dfhAlso);
                                    } else if (aCond.getThrough() != null && aCond.getThrough().getValue() != null
                                            && aCond.getThrough().getValue().getValueStmt() != null) {
                                        // WHEN ... ALSO <from> THRU <to>
                                        JsonObject rangeObj = new JsonObject();
                                        rangeObj.addProperty("from", insertSpaces(extractValueStmtText(alsoVs)));
                                        rangeObj.addProperty("thru", insertSpaces(extractValueStmtText(
                                                aCond.getThrough().getValue().getValueStmt())));
                                        alsoCondsArr.add(rangeObj);
                                    } else {
                                        alsoCondsArr.add(new JsonPrimitive(insertSpaces(extractValueStmtText(alsoVs))));
                                    }
                                } else if (acvs != null) {
                                    alsoCondsArr.add(new JsonPrimitive(insertSpaces(extractValueStmtText(acvs))));
                                } else if (aCond.getCtx() != null) {
                                    alsoCondsArr.add(new JsonPrimitive(insertSpaces(aCond.getCtx().getText())));
                                }
                            }
                        }
                        if (alsoCondsArr.size() > 0) whenObj.add("also_conditions", alsoCondsArr);
                    }

                    // Attach the phrase's shared body to each stacked WHEN. Only
                    // the first matching value's copy executes (each WHEN branches
                    // to the EVALUATE end after its body), so this duplicates the
                    // serialization but not the runtime behaviour.
                    if (hasBody) {
                        JsonArray whenStmts = serializeStatements(whenPhrase.getStatements());
                        if (whenStmts.size() > 0) whenObj.add("children", whenStmts);
                    }
                    children.add(whenObj);
                }
            }

            // WHEN OTHER
            io.proleap.cobol.asg.metamodel.procedure.evaluate.WhenOther whenOther = stmt.getWhenOther();
            if (whenOther != null && whenOther.getStatements() != null && !whenOther.getStatements().isEmpty()) {
                JsonObject whenOtherObj = newStatement("WHEN_OTHER");
                JsonArray otherStmts = serializeStatements(whenOther.getStatements());
                if (otherStmts.size() > 0) {
                    whenOtherObj.add("children", otherStmts);
                }
                children.add(whenOtherObj);
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
        // Distinguish EXIT (no-op paragraph terminator) from EXIT PROGRAM (return to caller).
        io.proleap.cobol.CobolParser.ExitStatementContext ctx =
                (io.proleap.cobol.CobolParser.ExitStatementContext) stmt.getCtx();
        if (ctx != null && ctx.PROGRAM() != null) {
            return newStatement("EXIT_PROGRAM");
        }
        return newStatement("EXIT");
    }

    private static JsonObject serializeGoback(GobackStatement stmt) {
        return newStatement("GOBACK");
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
                // One Sendings group may list several source operands sharing the
                // same DELIMITED BY phrase, e.g. STRING A B(1:2) DELIMITED BY SIZE.
                // Each operand must produce its own sending entry — taking only the
                // first dropped the rest (red-dragon-zuhj).
                DelimitedByPhrase dbp = sending.getDelimitedByPhrase();
                String delim = null;
                if (dbp != null) {
                    if (dbp.getDelimitedByType() == DelimitedByPhrase.DelimitedByType.SIZE) {
                        delim = "SIZE";
                    } else if (dbp.getCharactersValueStmt() != null) {
                        delim = extractValueStmtText(dbp.getCharactersValueStmt());
                    }
                }
                for (ValueStmt vs : sending.getSendingValueStmts()) {
                    JsonObject sendingObj = new JsonObject();
                    if (vs instanceof CallValueStmt) {
                        Call sendingCall = ((CallValueStmt) vs).getCall();
                        // A sending operand may itself be an intrinsic FUNCTION call,
                        // e.g. STRING FUNCTION TRIM(WS-VAR) ' ...' INTO WS-MSG. Serialize
                        // it structurally (function node) so the call is evaluated, not
                        // mistaken for a literal named "TRIM" (red-dragon-zuhj).
                        JsonObject fn = serializeFunctionNode(sendingCall);
                        sendingObj.add("value",
                                (fn != null) ? fn : serializeMoveOperand(sendingCall));
                    } else {
                        JsonObject litObj = new JsonObject();
                        litObj.addProperty("name", extractValueStmtText(vs));
                        sendingObj.add("value", litObj);
                    }
                    if (delim != null) {
                        sendingObj.addProperty("delimited_by", delim);
                    }
                    sendings.add(sendingObj);
                }
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
                obj.add("source", serializeMoveOperand(stmt.getSending().getSendingCall()));
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
                obj.add("source", serializeMoveOperand(stmt.getDataItemCall()));
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
            } else if (inspType == InspectStatement.InspectType.CONVERTING) {
                obj.addProperty("inspect_type", "CONVERTING");
                io.proleap.cobol.asg.metamodel.procedure.inspect.Converting conv =
                        stmt.getConverting();
                if (conv != null) {
                    if (conv.getFromValueStmt() != null) {
                        obj.addProperty("converting_from",
                                extractValueStmtText(conv.getFromValueStmt()));
                    }
                    if (conv.getTo() != null && conv.getTo().getToValueStmt() != null) {
                        obj.addProperty("converting_to",
                                extractValueStmtText(conv.getTo().getToValueStmt()));
                    }
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
                // Structured condition — same serializer the IF path uses.
                if (when.getCondition() != null) {
                    whenObj.add("condition", serializeConditionNode(when.getCondition()));
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
            // USING parameters — each BY REFERENCE/VALUE/CONTENT clause may carry
            // multiple operands (e.g. CALL 'X' USING BY REFERENCE WS-A WS-B).
            // Emit one JSON param object per operand, not one per clause.
            if (stmt.getUsingPhrase() != null && stmt.getUsingPhrase().getUsingParameters() != null) {
                JsonArray params = new JsonArray();
                for (UsingParameter param : stmt.getUsingPhrase().getUsingParameters()) {
                    if (param.getByReferencePhrase() != null
                            && param.getByReferencePhrase().getByReferences() != null) {
                        for (ByReference br : param.getByReferencePhrase().getByReferences()) {
                            JsonObject paramObj = new JsonObject();
                            paramObj.addProperty("type", "REFERENCE");
                            if (br.getByReferenceType() == ByReference.ByReferenceType.OMITTED) {
                                paramObj.addProperty("omitted", true);
                            } else {
                                paramObj.addProperty("name", extractValueStmtText(br.getValueStmt()));
                                if (br.getByReferenceType() == ByReference.ByReferenceType.STRING
                                        || br.getByReferenceType() == ByReference.ByReferenceType.INTEGER) {
                                    paramObj.addProperty("is_literal", true);
                                }
                            }
                            params.add(paramObj);
                        }
                    } else if (param.getByContentPhrase() != null
                            && param.getByContentPhrase().getByContents() != null) {
                        for (ByContent bc : param.getByContentPhrase().getByContents()) {
                            JsonObject paramObj = new JsonObject();
                            paramObj.addProperty("type", "CONTENT");
                            paramObj.addProperty("name", extractValueStmtText(bc.getValueStmt()));
                            if (bc.getValueStmt() instanceof io.proleap.cobol.asg.metamodel.valuestmt.LiteralValueStmt) {
                                paramObj.addProperty("is_literal", true);
                            }
                            params.add(paramObj);
                        }
                    } else if (param.getByValuePhrase() != null
                            && param.getByValuePhrase().getByValues() != null) {
                        for (ByValue bv : param.getByValuePhrase().getByValues()) {
                            JsonObject paramObj = new JsonObject();
                            paramObj.addProperty("type", "VALUE");
                            paramObj.addProperty("name", extractValueStmtText(bv.getValueStmt()));
                            if (bv.getValueStmt() instanceof io.proleap.cobol.asg.metamodel.valuestmt.LiteralValueStmt) {
                                paramObj.addProperty("is_literal", true);
                            }
                            params.add(paramObj);
                        }
                    }
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
            JsonArray modeGroups = new JsonArray();

            // INPUT files
            List<io.proleap.cobol.asg.metamodel.procedure.open.InputPhrase> inputPhrases = stmt.getInputPhrases();
            if (inputPhrases != null && !inputPhrases.isEmpty()) {
                JsonArray files = new JsonArray();
                inputPhrases.stream()
                    .flatMap(ip -> ip.getInputs().stream())
                    .map(io.proleap.cobol.asg.metamodel.procedure.open.Input::getFileCall)
                    .filter(c -> c != null)
                    .map(StatementSerializer::extractCallName)
                    .forEach(files::add);
                if (files.size() > 0) {
                    JsonObject grp = new JsonObject();
                    grp.addProperty("mode", "INPUT");
                    grp.add("files", files);
                    modeGroups.add(grp);
                }
            }

            // OUTPUT files
            List<io.proleap.cobol.asg.metamodel.procedure.open.OutputPhrase> outputPhrases = stmt.getOutputPhrases();
            if (outputPhrases != null && !outputPhrases.isEmpty()) {
                JsonArray files = new JsonArray();
                outputPhrases.stream()
                    .flatMap(op -> op.getOutputs().stream())
                    .map(io.proleap.cobol.asg.metamodel.procedure.open.Output::getFileCall)
                    .filter(c -> c != null)
                    .map(StatementSerializer::extractCallName)
                    .forEach(files::add);
                if (files.size() > 0) {
                    JsonObject grp = new JsonObject();
                    grp.addProperty("mode", "OUTPUT");
                    grp.add("files", files);
                    modeGroups.add(grp);
                }
            }

            // I-O files
            List<io.proleap.cobol.asg.metamodel.procedure.open.InputOutputPhrase> ioPhrases = stmt.getInputOutputPhrases();
            if (ioPhrases != null && !ioPhrases.isEmpty()) {
                JsonArray files = new JsonArray();
                ioPhrases.stream()
                    .flatMap(iop -> iop.getFileCalls().stream())
                    .map(StatementSerializer::extractCallName)
                    .forEach(files::add);
                if (files.size() > 0) {
                    JsonObject grp = new JsonObject();
                    grp.addProperty("mode", "I-O");
                    grp.add("files", files);
                    modeGroups.add(grp);
                }
            }

            // EXTEND files
            List<io.proleap.cobol.asg.metamodel.procedure.open.ExtendPhrase> extendPhrases = stmt.getExtendPhrases();
            if (extendPhrases != null && !extendPhrases.isEmpty()) {
                JsonArray files = new JsonArray();
                extendPhrases.stream()
                    .flatMap(ep -> ep.getFileCalls().stream())
                    .map(StatementSerializer::extractCallName)
                    .forEach(files::add);
                if (files.size() > 0) {
                    JsonObject grp = new JsonObject();
                    grp.addProperty("mode", "EXTEND");
                    grp.add("files", files);
                    modeGroups.add(grp);
                }
            }

            obj.add("mode_groups", modeGroups);
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

            // KEY IS clause
            io.proleap.cobol.asg.metamodel.procedure.read.Key key = stmt.getKey();
            if (key != null && key.getKeyCall() != null) {
                obj.addProperty("key", extractCallName(key.getKeyCall()));
            } else {
                obj.addProperty("key", "");
            }

            // AT END / NOT AT END
            io.proleap.cobol.asg.metamodel.procedure.AtEndPhrase atEnd = stmt.getAtEnd();
            if (atEnd != null && atEnd.getStatements() != null) {
                obj.add("at_end", serializeStatements(atEnd.getStatements()));
            } else {
                obj.add("at_end", new JsonArray());
            }
            io.proleap.cobol.asg.metamodel.procedure.NotAtEndPhrase notAtEnd = stmt.getNotAtEndPhrase();
            if (notAtEnd != null && notAtEnd.getStatements() != null) {
                obj.add("not_at_end", serializeStatements(notAtEnd.getStatements()));
            } else {
                obj.add("not_at_end", new JsonArray());
            }

            // INVALID KEY / NOT INVALID KEY
            io.proleap.cobol.asg.metamodel.procedure.InvalidKeyPhrase invalidKey = stmt.getInvalidKeyPhrase();
            if (invalidKey != null && invalidKey.getStatements() != null) {
                obj.add("invalid_key", serializeStatements(invalidKey.getStatements()));
            } else {
                obj.add("invalid_key", new JsonArray());
            }
            io.proleap.cobol.asg.metamodel.procedure.NotInvalidKeyPhrase notInvalidKey = stmt.getNotInvalidKeyPhrase();
            if (notInvalidKey != null && notInvalidKey.getStatements() != null) {
                obj.add("not_invalid_key", serializeStatements(notInvalidKey.getStatements()));
            } else {
                obj.add("not_invalid_key", new JsonArray());
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

            // INVALID KEY / NOT INVALID KEY
            io.proleap.cobol.asg.metamodel.procedure.InvalidKeyPhrase invalidKey = stmt.getInvalidKeyPhrase();
            if (invalidKey != null && invalidKey.getStatements() != null) {
                obj.add("invalid_key", serializeStatements(invalidKey.getStatements()));
            } else {
                obj.add("invalid_key", new JsonArray());
            }
            io.proleap.cobol.asg.metamodel.procedure.NotInvalidKeyPhrase notInvalidKey = stmt.getNotInvalidKeyPhrase();
            if (notInvalidKey != null && notInvalidKey.getStatements() != null) {
                obj.add("not_invalid_key", serializeStatements(notInvalidKey.getStatements()));
            } else {
                obj.add("not_invalid_key", new JsonArray());
            }
        } catch (Exception e) {
            LOG.fine("Could not extract WRITE operands: " + e.getMessage());
        }
        return obj;
    }

    private static JsonObject serializeRewrite(RewriteStatement stmt) {
        JsonObject obj = newStatement("REWRITE");
        try {
            if (stmt.getRecordCall() != null) {
                obj.addProperty("record_name", extractCallName(stmt.getRecordCall()));
            }
            io.proleap.cobol.asg.metamodel.procedure.rewrite.From from = stmt.getFrom();
            if (from != null && from.getFromCall() != null) {
                obj.addProperty("from_field", extractCallName(from.getFromCall()));
            }

            // INVALID KEY / NOT INVALID KEY
            io.proleap.cobol.asg.metamodel.procedure.InvalidKeyPhrase invalidKey = stmt.getInvalidKeyPhrase();
            if (invalidKey != null && invalidKey.getStatements() != null) {
                obj.add("invalid_key", serializeStatements(invalidKey.getStatements()));
            } else {
                obj.add("invalid_key", new JsonArray());
            }
            io.proleap.cobol.asg.metamodel.procedure.NotInvalidKeyPhrase notInvalidKey = stmt.getNotInvalidKeyPhrase();
            if (notInvalidKey != null && notInvalidKey.getStatements() != null) {
                obj.add("not_invalid_key", serializeStatements(notInvalidKey.getStatements()));
            } else {
                obj.add("not_invalid_key", new JsonArray());
            }
        } catch (Exception e) {
            LOG.fine("Could not extract REWRITE operands: " + e.getMessage());
        }
        return obj;
    }

    private static JsonObject serializeStart(StartStatement stmt) {
        JsonObject obj = newStatement("START");
        try {
            if (stmt.getFileCall() != null) {
                obj.addProperty("file_name", extractCallName(stmt.getFileCall()));
            }
            io.proleap.cobol.asg.metamodel.procedure.start.Key key = stmt.getKey();
            if (key != null && key.getComparisonCall() != null) {
                obj.addProperty("key", extractCallName(key.getComparisonCall()));
                // Relational operator from KeyType enum
                if (key.getKeyType() != null) {
                    String relop;
                    switch (key.getKeyType()) {
                        case GREATER: relop = ">"; break;
                        case GREATER_OR_EQUAL: relop = ">="; break;
                        case EQUAL: default: relop = "="; break;
                    }
                    obj.addProperty("relop", relop);
                } else {
                    obj.addProperty("relop", "=");
                }
            }

            // INVALID KEY / NOT INVALID KEY
            io.proleap.cobol.asg.metamodel.procedure.InvalidKeyPhrase invalidKey = stmt.getInvalidKeyPhrase();
            if (invalidKey != null && invalidKey.getStatements() != null) {
                obj.add("invalid_key", serializeStatements(invalidKey.getStatements()));
            } else {
                obj.add("invalid_key", new JsonArray());
            }
            io.proleap.cobol.asg.metamodel.procedure.NotInvalidKeyPhrase notInvalidKey = stmt.getNotInvalidKeyPhrase();
            if (notInvalidKey != null && notInvalidKey.getStatements() != null) {
                obj.add("not_invalid_key", serializeStatements(notInvalidKey.getStatements()));
            } else {
                obj.add("not_invalid_key", new JsonArray());
            }
        } catch (Exception e) {
            LOG.fine("Could not extract START operands: " + e.getMessage());
        }
        return obj;
    }

    private static JsonObject serializeDelete(DeleteStatement stmt) {
        JsonObject obj = newStatement("DELETE");
        try {
            if (stmt.getFileCall() != null) {
                obj.addProperty("file_name", extractCallName(stmt.getFileCall()));
            }

            // INVALID KEY / NOT INVALID KEY
            io.proleap.cobol.asg.metamodel.procedure.InvalidKeyPhrase invalidKey = stmt.getInvalidKeyPhrase();
            if (invalidKey != null && invalidKey.getStatements() != null) {
                obj.add("invalid_key", serializeStatements(invalidKey.getStatements()));
            } else {
                obj.add("invalid_key", new JsonArray());
            }
            io.proleap.cobol.asg.metamodel.procedure.NotInvalidKeyPhrase notInvalidKey = stmt.getNotInvalidKeyPhrase();
            if (notInvalidKey != null && notInvalidKey.getStatements() != null) {
                obj.add("not_invalid_key", serializeStatements(notInvalidKey.getStatements()));
            } else {
                obj.add("not_invalid_key", new JsonArray());
            }
        } catch (Exception e) {
            LOG.fine("Could not extract DELETE operands: " + e.getMessage());
        }
        return obj;
    }

    private static JsonObject serializeExecCics(ExecCicsStatement stmt) {
        JsonObject obj = newStatement("EXEC_CICS");
        String text = stmt.getExecCicsText();
        if (text != null) {
            obj.addProperty("exec_cics_text", text);
        }
        return obj;
    }

    private static JsonObject serializeExecSql(ExecSqlStatement stmt) {
        // Opaque passthrough, exactly like serializeExecCics: emit getExecSqlText()
        // verbatim (the full "EXEC SQL ... END-EXEC" form). The bridge does no SQL
        // parsing; envelope removal + parsing happen in the Python/squall layer.
        JsonObject obj = newStatement("EXEC_SQL");
        String text = stmt.getExecSqlText();
        if (text != null) {
            obj.addProperty("exec_sql_text", text);
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
    static String extractCallName(Call call) {
        if (call == null) {
            return "";
        }
        // Unwrap delegate calls to reach the actual underlying call
        Call unwrapped = call.unwrap();

        // A TABLE_CALL is a subscripted reference; emit the BARE base name. The
        // subscripts travel separately (see extractSubscripts / serializeRef);
        // they are no longer flattened into the name string. (red-dragon-6ddr)
        if (unwrapped.getCallType() == Call.CallType.TABLE_CALL && unwrapped instanceof TableCall tableCall) {
            String baseName = tableCall.getName();
            return (baseName != null) ? baseName : unwrapped.toString();
        }

        String name = call.getName();
        if (name != null) {
            return name;
        }
        // ProLeap does not model COBOL special registers (RETURN-CODE, SORT-RETURN,
        // TALLY, ...) as data items, so the Call's getName() is null. Recover the
        // verbatim source identifier from the parse-tree context (e.g. the literal
        // text "RETURN-CODE") so the frontend can route it; without this the name
        // degrades to the opaque call.toString() ("name=[null]"). (red-dragon-o8uq)
        String ctxText = callContextText(unwrapped);
        return (ctxText != null) ? ctxText : call.toString();
    }

    /** First parse-tree token text of a Call's grammar context, or null. */
    private static String callContextText(Call call) {
        if (!(call instanceof ASGElementImpl)) {
            return null;
        }
        ParserRuleContext ctx = ((ASGElementImpl) call).getCtx();
        if (ctx == null || ctx.getStart() == null) {
            return null;
        }
        return ctx.getStart().getText();
    }

    /**
     * All subscripts of a (possibly delegated) TABLE_CALL, in source order, each
     * as a STRUCTURED expression node ({@code {kind:"ref"/"lit"/"binop"/...}}) —
     * the same shape the COMPUTE/IF value-stmt serializer emits and that the
     * Python {@code expr_from_dict} consumes. Reuses {@link #serializeFromValue}
     * so an arithmetic or nested subscript (e.g. {@code TBL(WS-I + 1)}) is carried
     * as a real expression tree, not a string (red-dragon-l445). Empty array for
     * any non-table call.
     */
    private static JsonArray extractSubscripts(Call call) {
        JsonArray arr = new JsonArray();
        if (call == null) {
            return arr;
        }
        Call unwrapped = call.unwrap();
        if (unwrapped.getCallType() == Call.CallType.TABLE_CALL && unwrapped instanceof TableCall tableCall) {
            List<Subscript> subscripts = tableCall.getSubscripts();
            if (subscripts != null) {
                for (Subscript sub : subscripts) {
                    arr.add(serializeFromValue(sub.getSubscriptValueStmt()));
                }
            }
        }
        return arr;
    }

    /**
     * Structured reference operand: {@code {name: <bare base>, subscripts:[...],
     * ref_mod_start?, ref_mod_length?, qualifiers?}}. Subscripts and ref-mod keys
     * are present only when non-empty. The single serializer for any subscriptable
     * data reference. (red-dragon-6ddr)
     */
    private static JsonObject serializeRef(Call call) {
        JsonObject obj = new JsonObject();
        obj.addProperty("name", extractCallName(call));
        JsonArray subs = extractSubscripts(call);
        if (subs.size() > 0) {
            obj.add("subscripts", subs);
        }
        CobolParser.ReferenceModifierContext refMod = getRefMod(call);
        if (refMod != null) {
            JsonObject rm = serializeRefMod(refMod);
            obj.add("ref_mod_start", rm.get("ref_mod_start"));
            if (rm.has("ref_mod_length")) {
                obj.add("ref_mod_length", rm.get("ref_mod_length"));
            }
        }
        JsonArray qualifiers = extractQualifiers(call);
        if (qualifiers.size() > 0) {
            obj.add("qualifiers", qualifiers);
        }
        return obj;
    }

    /**
     * Navigates a Call's grammar context to find its referenceModifier, or null if absent.
     * ProLeap models ref-mod fields as TABLE_CALL; the grammar context has tableCall().referenceModifier().
     */
    private static CobolParser.ReferenceModifierContext getRefMod(Call call) {
        if (call == null) return null;
        Call unwrapped = call.unwrap();
        if (!(unwrapped instanceof ASGElementImpl)) return null;
        ParserRuleContext ctx = ((ASGElementImpl) unwrapped).getCtx();
        if (ctx == null) return null;

        // If ctx is already a TableCallContext, call referenceModifier() directly
        if (ctx instanceof CobolParser.TableCallContext) {
            CobolParser.ReferenceModifierContext direct =
                    ((CobolParser.TableCallContext) ctx).referenceModifier();
            if (direct != null) return direct;
        }

        // Otherwise, try to find tableCall() method (e.g. for IdentifierContext)
        try {
            java.lang.reflect.Method m = ctx.getClass().getMethod("tableCall");
            CobolParser.TableCallContext tc = (CobolParser.TableCallContext) m.invoke(ctx);
            if (tc != null) {
                CobolParser.ReferenceModifierContext rm = tc.referenceModifier();
                if (rm != null) return rm;
            }
        } catch (Exception e) {
            // ctx may not have a tableCall() method (e.g. if it's not an identifierContext);
            // reflection lets us probe without a compile-time cast — fall through.
        }

        // A QUALIFIED data reference (X OF Y(2:8)) wraps the tableCall +
        // referenceModifier deeper in the parse tree (qualifiedDataName), so the
        // direct/tableCall() lookups above miss it. Search the subtree for the
        // first ReferenceModifierContext. (CardDemo COTRN02C: TRNAMTI OF COTRN2AI.)
        return firstReferenceModifierDescendant(ctx);
    }

    /** Depth-first search for the first ReferenceModifierContext descendant. */
    private static CobolParser.ReferenceModifierContext firstReferenceModifierDescendant(
            ParserRuleContext ctx) {
        if (ctx == null) {
            return null;
        }
        for (int i = 0; i < ctx.getChildCount(); i++) {
            org.antlr.v4.runtime.tree.ParseTree child = ctx.getChild(i);
            if (child instanceof CobolParser.ReferenceModifierContext) {
                return (CobolParser.ReferenceModifierContext) child;
            }
            if (child instanceof ParserRuleContext) {
                CobolParser.ReferenceModifierContext found =
                        firstReferenceModifierDescendant((ParserRuleContext) child);
                if (found != null) {
                    return found;
                }
            }
        }
        return null;
    }

    /**
     * Extracts the base data name for a call, stripping subscript/refmod notation.
     * For TABLE_CALL: uses the first token of the grammar context (the data name token).
     * Falls back to extractCallName for non-TABLE_CALL types.
     */
    private static String extractCallBaseName(Call call) {
        if (call == null) return "";
        Call unwrapped = call.unwrap();
        if (unwrapped.getCallType() == Call.CallType.TABLE_CALL && unwrapped instanceof ASGElementImpl) {
            ParserRuleContext ctx = ((ASGElementImpl) unwrapped).getCtx();
            if (ctx != null) {
                org.antlr.v4.runtime.Token start = ctx.getStart();
                if (start != null) return start.getText();
            }
        }
        String name = call.getName();
        return (name != null) ? name : call.toString();
    }

    /**
     * Serializes a PERFORM VARYING FROM value as a structured expression node so
     * the Python frontend can evaluate it (rather than treating the flattened text
     * as an opaque literal). Recognises {@code LENGTH OF <field>} structurally from
     * the parse-tree special-register context, emitting
     * {@code {"kind":"length_of","name":"<field>"}}. Otherwise serializes the
     * underlying arithmetic expression (refs, literals, ref-mod, binops); failing
     * that, falls back to a {@code {"kind":"lit","value":<text>}} node.
     */
    /**
     * If a MOVE sending-area ValueStmt is a {@code LENGTH OF <field>} special
     * register, returns a structured {@code {"kind":"length_of","name":"<field>"}}
     * node (the leaf data-name); otherwise returns {@code null}. Structural — no
     * text parsing. Mirrors {@link #serializeFromValue}'s length_of handling.
     */
    private static JsonObject serializeMoveLengthOfSource(ValueStmt vs) {
        if (vs == null) {
            return null;
        }
        ParserRuleContext ctx;
        try {
            ctx = vs.getCtx();
        } catch (Exception e) {
            return null;
        }
        if (ctx == null) {
            return null;
        }
        // A `LENGTH OF G` appearing INSIDE a reference modifier (e.g.
        // MOVE SRC(1:LENGTH OF G) TO ...) is the slice length, not the sending
        // operand — leave it for the ref-mod path. Only treat the source as a
        // LENGTH OF value when no referenceModifier wraps it. (red-dragon)
        if (firstReferenceModifierDescendant(ctx) != null) {
            return null;
        }
        CobolParser.SpecialRegisterContext sr = findLengthOfSpecialRegister(ctx);
        if (sr == null) {
            return null;
        }
        JsonObject obj = new JsonObject();
        obj.addProperty("kind", "length_of");
        CobolParser.IdentifierContext id = sr.identifier();
        obj.addProperty("name", id != null ? leafDataName(id) : "");
        return obj;
    }

    private static JsonElement serializeFromValue(ValueStmt vs) {
        if (vs == null) {
            return litNode("");
        }
        ParserRuleContext ctx = null;
        try {
            ctx = vs.getCtx();
        } catch (Exception e) {
            // fall through
        }
        if (ctx != null) {
            CobolParser.SpecialRegisterContext sr = findLengthOfSpecialRegister(ctx);
            if (sr != null) {
                JsonObject obj = new JsonObject();
                obj.addProperty("kind", "length_of");
                CobolParser.IdentifierContext id = sr.identifier();
                // Use the LEAF data-name for a qualified operand (WS-SUB OF
                // WS-GRP -> "WS-SUB"); getText() would glue it to
                // "WS-SUBOFWS-GRP", which the frontend can't resolve (length 0).
                // Mirrors serializeBasisCtx's length_of handling. (red-dragon)
                obj.addProperty("name", id != null ? leafDataName(id) : "");
                return obj;
            }
        }
        if (vs instanceof ArithmeticValueStmt) {
            return serializeArithmeticExpr((ArithmeticValueStmt) vs);
        }
        // Bare field reference / literal — keep structured so the Python side can
        // decide between field decode and literal parse.
        String text = (ctx != null) ? ctx.getText() : extractValueStmtText(vs);
        JsonObject ref = new JsonObject();
        ref.addProperty("kind", "ref");
        ref.addProperty("name", text);
        return ref;
    }

    /**
     * Recursively searches a parse-tree context for a {@code LENGTH OF}
     * specialRegister (a SpecialRegisterContext whose LENGTH() token is present),
     * returning it or {@code null}. Structural — no text parsing.
     */
    private static CobolParser.SpecialRegisterContext findLengthOfSpecialRegister(
            org.antlr.v4.runtime.tree.ParseTree node) {
        if (node == null) {
            return null;
        }
        if (node instanceof CobolParser.SpecialRegisterContext) {
            CobolParser.SpecialRegisterContext sr = (CobolParser.SpecialRegisterContext) node;
            if (sr.LENGTH() != null) {
                return sr;
            }
        }
        for (int i = 0; i < node.getChildCount(); i++) {
            CobolParser.SpecialRegisterContext found = findLengthOfSpecialRegister(node.getChild(i));
            if (found != null) {
                return found;
            }
        }
        return null;
    }

    /**
     * Serializes a referenceModifier context to a JsonObject with ref_mod_start
     * and optionally ref_mod_length (key absent when length is omitted in source).
     */
    private static JsonObject serializeRefMod(CobolParser.ReferenceModifierContext refMod) {
        JsonObject obj = new JsonObject();
        CobolParser.CharacterPositionContext charPos = refMod.characterPosition();
        obj.add("ref_mod_start",
            (charPos != null) ? serializeArithExprCtx(charPos.arithmeticExpression()) : litNode(""));
        CobolParser.LengthContext len = refMod.length();
        if (len != null) {
            obj.add("ref_mod_length",
                serializeArithExprCtx(len.arithmeticExpression()));
        }
        return obj;
    }

    /**
     * Serializes a MOVE operand Call to {name, ref_mod_start?, ref_mod_length?}.
     * ref_mod keys are absent (not null) when no reference modification is present.
     */
    private static JsonObject serializeMoveOperand(Call call) {
        // Unified structured-reference serializer (name + subscripts + ref-mod +
        // qualifiers). (red-dragon-6ddr)
        return serializeRef(call);
    }

    /**
     * Extracts the {@code OF}/{@code IN} qualifier data names for a Call (e.g.
     * {@code VSTRING-LENGTH OF WS-DATE-TO-TEST} -> ["WS-DATE-TO-TEST"]), in the
     * order written (immediate enclosing group first). COBOL allows duplicate
     * elementary names disambiguated by qualification (CardDemo CSUTLDTC's two
     * Vstring groups), and {@code extractCallName} returns only the leaf, so the
     * qualifiers are carried separately for the frontend to resolve against the
     * named ancestor group. Structural walk of the parse tree — no text parsing.
     */
    private static JsonArray extractQualifiers(Call call) {
        JsonArray qualifiers = new JsonArray();
        if (call == null) {
            return qualifiers;
        }
        Call unwrapped = call.unwrap();
        if (!(unwrapped instanceof ASGElementImpl)) {
            return qualifiers;
        }
        ParserRuleContext ctx = ((ASGElementImpl) unwrapped).getCtx();
        if (ctx == null) {
            return qualifiers;
        }
        collectInDataQualifiers(ctx, qualifiers);
        return qualifiers;
    }

    private static void collectInDataQualifiers(
            org.antlr.v4.runtime.tree.ParseTree node, JsonArray out) {
        if (node == null) {
            return;
        }
        if (node instanceof CobolParser.InDataContext) {
            CobolParser.DataNameContext dn = ((CobolParser.InDataContext) node).dataName();
            if (dn != null) {
                out.add(dn.getText());
            }
        }
        for (int i = 0; i < node.getChildCount(); i++) {
            collectInDataQualifiers(node.getChild(i), out);
        }
    }


    /**
     * Serializes an arithmetic source operand ValueStmt.
     * Returns a JsonElement: either a JsonObject with {name, ref_mod_start?, ref_mod_length?}
     * for Call-based operands, or a string for literals.
     */
    private static JsonElement serializeArithSource(ValueStmt vs) {
        if (vs instanceof CallValueStmt) {
            Call c = ((CallValueStmt) vs).getCall();
            JsonObject fn = serializeFunctionNode(c);
            if (fn != null) {
                return fn;
            }
            return serializeMoveOperand(c);
        }
        if (vs instanceof LiteralValueStmt) {
            JsonObject dfh = serializeDfhrespLit((LiteralValueStmt) vs);
            if (dfh != null) return dfh;
        }
        // For literals and other operands, return as plain string
        return new JsonPrimitive(extractValueStmtText(vs));
    }

    /**
     * Locates the {@link CobolParser.FunctionCallContext} reachable from a Call's
     * grammar context, if any. COBOL intrinsic functions (FUNCTION UPPER-CASE(...))
     * surface as a FUNCTION_CALL whose ctx is — or contains — a FunctionCallContext.
     *
     * @return the FunctionCallContext, or {@code null} when the call is not a function.
     */
    private static CobolParser.FunctionCallContext findFunctionCallCtx(Call call) {
        if (call == null) {
            return null;
        }
        Call unwrapped = call.unwrap();
        if (!(unwrapped instanceof ASGElementImpl)) {
            return null;
        }
        ParserRuleContext ctx = ((ASGElementImpl) unwrapped).getCtx();
        return findFunctionCallCtx(ctx);
    }

    /**
     * Walks a grammar context (and its ancestors/descendants) to find a
     * FunctionCallContext. ProLeap may attach the call to an identifier-shaped
     * context whose subtree (or parent) holds the actual functionCall rule.
     */
    private static CobolParser.FunctionCallContext findFunctionCallCtx(ParserRuleContext ctx) {
        if (ctx == null) {
            return null;
        }
        if (ctx instanceof CobolParser.FunctionCallContext) {
            return (CobolParser.FunctionCallContext) ctx;
        }
        // Search ancestors (the Call ctx may be a child of the functionCall rule).
        for (ParserRuleContext p = ctx.getParent(); p != null; p = p.getParent()) {
            if (p instanceof CobolParser.FunctionCallContext) {
                return (CobolParser.FunctionCallContext) p;
            }
        }
        // Search descendants (the functionCall rule may be nested under ctx).
        return ctx.getRuleContext(CobolParser.FunctionCallContext.class, 0) != null
                ? ctx.getRuleContext(CobolParser.FunctionCallContext.class, 0)
                : firstFunctionCallDescendant(ctx);
    }

    /**
     * Finds a FunctionCallContext at {@code ctx} itself or among its descendants
     * ONLY (never ancestors). Used when serializing a basis operand: a basis that
     * IS a function call must serialize structurally, but a basis that is a plain
     * ref nested inside a larger function call must NOT be mistaken for one.
     */
    private static CobolParser.FunctionCallContext findFunctionCallCtxInSubtree(ParserRuleContext ctx) {
        if (ctx == null) {
            return null;
        }
        if (ctx instanceof CobolParser.FunctionCallContext) {
            return (CobolParser.FunctionCallContext) ctx;
        }
        return firstFunctionCallDescendant(ctx);
    }

    /** Depth-first search for the first FunctionCallContext descendant. */
    private static CobolParser.FunctionCallContext firstFunctionCallDescendant(ParserRuleContext ctx) {
        if (ctx == null) {
            return null;
        }
        for (int i = 0; i < ctx.getChildCount(); i++) {
            org.antlr.v4.runtime.tree.ParseTree child = ctx.getChild(i);
            if (child instanceof CobolParser.FunctionCallContext) {
                return (CobolParser.FunctionCallContext) child;
            }
            if (child instanceof ParserRuleContext) {
                CobolParser.FunctionCallContext found =
                        firstFunctionCallDescendant((ParserRuleContext) child);
                if (found != null) {
                    return found;
                }
            }
        }
        return null;
    }


    /**
     * Serializes a COBOL intrinsic FUNCTION call to a structured node:
     * {@code {"kind":"function","name":"UPPER-CASE","args":[<operand>, ...]}}.
     *
     * <p>The function name and arguments are read from the grammar context for
     * fidelity (ProLeap models the call as a thin marker without structured args).
     * Each argument is serialized with the existing operand/expression serializers.
     *
     * @return the function node, or {@code null} when {@code call} is not a function call.
     */
    /**
     * Like {@link #serializeFunctionNode(Call)} but probes a ValueStmt's own
     * grammar context. Some intrinsic forms (notably the no-argument
     * FUNCTION CURRENT-DATE) do not surface as a CallValueStmt; the functionCall
     * rule is reachable from the ValueStmt's ctx instead.
     */
    private static JsonObject serializeFunctionNodeFromValueStmt(ValueStmt vs) {
        if (vs == null) {
            return null;
        }
        ParserRuleContext ctx = vs.getCtx();
        CobolParser.FunctionCallContext fc = findFunctionCallCtx(ctx);
        return serializeFunctionNodeFromCtx(fc);
    }

    private static JsonObject serializeFunctionNode(Call call) {
        CobolParser.FunctionCallContext fc = findFunctionCallCtx(call);
        return serializeFunctionNodeFromCtx(fc);
    }

    private static JsonObject serializeFunctionNodeFromCtx(CobolParser.FunctionCallContext fc) {
        if (fc == null) {
            return null;
        }
        JsonObject obj = new JsonObject();
        obj.addProperty("kind", "function");
        String name = (fc.functionName() != null) ? fc.functionName().getText() : "";
        obj.addProperty("name", name.toUpperCase());
        JsonArray args = new JsonArray();
        for (CobolParser.ArgumentContext arg : fc.argument()) {
            args.add(serializeFunctionArg(arg));
        }
        obj.add("args", args);
        return obj;
    }

    /**
     * Serializes a single intrinsic-function argument to an expression node,
     * reusing the arithmetic-expression serializer for fidelity. Falls back to a
     * plain ref/literal node when no arithmeticExpression sub-rule is present.
     */
    private static JsonElement serializeFunctionArg(CobolParser.ArgumentContext arg) {
        if (arg == null) {
            return litNode("");
        }
        // Every argument is now an arithmeticExpression (grammar:
        // argument : arithmeticExpression | qualifiedDataName ... | indexName ...).
        // serializeArithExprCtx -> ... -> serializeBasisCtx recursively handles
        // nested FUNCTION calls (red-dragon-ge72), reference modification
        // (red-dragon-74qu), LENGTH OF, figuratives, and builds the +/- and */÷
        // binop tree. So an arithmetic argument like F(a - 1) serialises as a
        // binop with the nested function inside it, instead of being collapsed to
        // just its inner function (red-dragon-zgwl). No subtree short-circuit.
        if (arg.arithmeticExpression() != null) {
            return serializeArithExprCtx(arg.arithmeticExpression());
        }
        if (arg.qualifiedDataName() != null) {
            JsonObject ref = new JsonObject();
            ref.addProperty("kind", "ref");
            ref.addProperty("name", arg.qualifiedDataName().getText());
            return ref;
        }
        return litNode(arg.getText());
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
     * Serializes a ConditionValueStmt into a structured JSON tree.
     *
     * <p>Single-atom conditions produce a combinable-condition object directly.
     * Compound conditions (AND/OR chains) produce a left-folded binary tree:
     * {@code {"op": "AND", "left": {...}, "right": {...}}}.
     */
    private static JsonObject serializeConditionNode(ConditionValueStmt cond) {
        CombinableCondition firstCc = cond.getCombinableCondition();
        JsonObject current = serializeCombinableCondition(firstCc);

        // Track the inherited subject + operator for abbreviated operands.
        // In "A = X OR Y", the trailing "Y" inherits subject A and operator "=".
        JsonElement subjectExpr = relationSubjectExpr(firstCc);
        String subjectOp = relationSubjectOp(firstCc);

        for (AndOrCondition aoc : cond.getAndOrConditions()) {
            String boolOp = (aoc.getAndOrConditionType() == AndOrCondition.AndOrConditionType.AND)
                    ? "AND" : "OR";
            JsonObject right;
            CombinableCondition rightCc = aoc.getCombinableCondition();
            if (rightCc != null) {
                right = serializeCombinableCondition(rightCc);
                JsonElement nextSubj = relationSubjectExpr(rightCc);
                if (nextSubj != null) {
                    subjectExpr = nextSubj;
                    subjectOp = relationSubjectOp(rightCc);
                }
            } else {
                // Abbreviated operand(s): inherit subject + operator.
                right = serializeAbbreviations(aoc, subjectExpr, subjectOp, boolOp);
            }
            JsonObject compound = new JsonObject();
            compound.addProperty("op", boolOp);
            compound.add("left", current);
            compound.add("right", right);
            current = compound;
        }
        return current;
    }

    /**
     * Returns the left-hand arithmetic expression of a combinable condition's
     * ARITHMETIC relation (the abbreviation subject), or {@code null} if absent.
     */
    private static JsonElement relationSubjectExpr(CombinableCondition cc) {
        ArithmeticComparison ac = arithmeticComparisonOf(cc);
        if (ac == null || ac.getArithmeticExpressionLeft() == null) {
            return null;
        }
        return serializeArithmeticExpr(ac.getArithmeticExpressionLeft());
    }

    /** Returns the relational operator of a combinable condition's ARITHMETIC relation. */
    private static String relationSubjectOp(CombinableCondition cc) {
        ArithmeticComparison ac = arithmeticComparisonOf(cc);
        return ac != null ? relationalOpToString(ac.getOperator()) : "==";
    }

    private static ArithmeticComparison arithmeticComparisonOf(CombinableCondition cc) {
        if (cc == null || cc.getSimpleCondition() == null) {
            return null;
        }
        SimpleCondition sc = cc.getSimpleCondition();
        if (sc.getSimpleConditionType() != SimpleCondition.SimpleConditionType.RELATION_CONDITION) {
            return null;
        }
        RelationConditionValueStmt rel = sc.getRelationCondition();
        if (rel == null
                || rel.getRelationConditionType() != RelationConditionValueStmt.RelationConditionType.ARITHMETIC) {
            return null;
        }
        return rel.getArithmeticComparison();
    }

    /**
     * Builds the right-hand condition node for an abbreviated AndOrCondition whose
     * operands inherit the subject expression and operator from the preceding
     * relation. Each abbreviation may override the operator (e.g. {@code A = X OR > Y}).
     */
    private static JsonObject serializeAbbreviations(
            AndOrCondition aoc, JsonElement subjectExpr, String inheritedOp, String boolOp) {
        java.util.List<io.proleap.cobol.asg.metamodel.valuestmt.relation.Abbreviation> abbrevs =
                aoc.getAbbreviations();
        if (subjectExpr == null || abbrevs == null || abbrevs.isEmpty()) {
            JsonObject obj = new JsonObject();
            obj.addProperty("text", "");
            return obj;
        }
        JsonObject current = null;
        for (io.proleap.cobol.asg.metamodel.valuestmt.relation.Abbreviation abbr : abbrevs) {
            String op = abbr.getOperator() != null
                    ? relationalOpToString(abbr.getOperator()) : inheritedOp;
            JsonElement operand = abbr.getArithmeticExpression() != null
                    ? serializeArithmeticExpr(abbr.getArithmeticExpression()) : litNode("");

            JsonObject relation = new JsonObject();
            relation.add("left", subjectExpr);
            relation.addProperty("op", op);
            relation.add("right", operand);

            JsonObject atom = new JsonObject();
            atom.addProperty("not", false);
            atom.add("relation", relation);

            if (current == null) {
                current = atom;
            } else {
                JsonObject compound = new JsonObject();
                compound.addProperty("op", boolOp);
                compound.add("left", current);
                compound.add("right", atom);
                current = compound;
            }
        }
        return current;
    }

    /**
     * Serializes a single CombinableCondition (one atom, possibly negated).
     *
     * <p>Result shapes:
     * <ul>
     *   <li>{@code {"not": bool, "condition_name": "IS-MINOR"}} for 88-level references</li>
     *   <li>{@code {"not": bool, "relation": {"left": <expr>, "op": "...", "right": <expr>}}} for relation conditions</li>
     *   <li>{@code {"not": bool, "text": "..."}} fallback for class/sign/unknown conditions</li>
     *   <li>{@code {"not": bool, "condition": {...}}} for nested parenthesised conditions</li>
     * </ul>
     */
    private static JsonObject serializeCombinableCondition(CombinableCondition cc) {
        JsonObject obj = new JsonObject();
        if (cc == null) {
            obj.addProperty("text", "");
            return obj;
        }
        boolean not = cc.isNot();
        obj.addProperty("not", not);

        SimpleCondition sc = cc.getSimpleCondition();
        if (sc == null) {
            obj.addProperty("text", "");
            return obj;
        }

        SimpleCondition.SimpleConditionType scType = sc.getSimpleConditionType();
        if (scType == SimpleCondition.SimpleConditionType.CONDITION_NAME_REFERENCE) {
            ConditionNameReference ref = sc.getConditionNameReference();
            if (ref != null && ref.getConditionCall() != null) {
                obj.addProperty("condition_name", extractCallName(ref.getConditionCall()));
            } else {
                obj.addProperty("text", insertSpaces(sc.getCtx().getText()));
            }
        } else if (scType == SimpleCondition.SimpleConditionType.CONDITION) {
            ConditionValueStmt nested = sc.getCondition();
            if (nested != null) {
                obj.add("condition", serializeConditionNode(nested));
            } else {
                obj.addProperty("text", "");
            }
        } else if (scType == SimpleCondition.SimpleConditionType.RELATION_CONDITION) {
            RelationConditionValueStmt rel = sc.getRelationCondition();
            if (rel == null) {
                obj.addProperty("text", insertSpaces(sc.getCtx().getText()));
            } else if (rel.getRelationConditionType()
                    == RelationConditionValueStmt.RelationConditionType.COMBINED) {
                // Abbreviated comparison (A = X OR Y): expand into the AND/OR tree.
                JsonObject expanded = serializeCombinedComparison(rel.getCombinedComparison());
                if (expanded != null) {
                    // Wrap the expanded tree as a nested condition so the surrounding
                    // 'not' flag still applies via the {not, condition} shape.
                    obj.add("condition", expanded);
                } else {
                    obj.addProperty("text", insertSpaces(sc.getCtx().getText()));
                }
            } else if (rel.getRelationConditionType()
                    == RelationConditionValueStmt.RelationConditionType.SIGN) {
                serializeSignCondition(obj, sc, not);
            } else {
                obj.add("relation", serializeRelationCondition(rel));
            }
        } else if (scType == SimpleCondition.SimpleConditionType.CLASS_CONDITION) {
            serializeClassCondition(obj, sc, not);
        } else {
            // Unknown — fall back to text
            obj.addProperty("text", insertSpaces(sc.getCtx().getText()));
        }

        return obj;
    }

    /**
     * Populates {@code obj} for a CLASS_CONDITION, emitting the structured
     * {@code {"not": bool, "class": "NUMERIC"|..., "operand": <expr>}} shape.
     *
     * <p>COBOL {@code X IS NOT NUMERIC} may carry the negation on the enclosing
     * CombinableCondition ({@code ccNot}) and/or the ClassCondition itself; the
     * effective negation is their XOR. If the class type or operand is not
     * supported, falls back to the existing text path for this node only.
     */
    private static void serializeClassCondition(JsonObject obj, SimpleCondition sc, boolean ccNot) {
        ClassCondition cls = sc.getClassCondition();
        if (cls == null) {
            obj.addProperty("text", insertSpaces(sc.getCtx().getText()));
            return;
        }
        String className = classConditionTypeToString(cls.getClassConditionType());
        if (className == null || cls.getIdentifierCall() == null) {
            obj.addProperty("text", insertSpaces(sc.getCtx().getText()));
            return;
        }
        boolean effectiveNot = ccNot ^ cls.getNot();
        obj.addProperty("not", effectiveNot);
        obj.addProperty("class", className);
        // The operand may be reference-modified, e.g.
        // WS-FIELD(1:WS-LEN) IS NUMERIC. serializeMoveOperand captures both the
        // name and any ref_mod_start/ref_mod_length so the class test runs over
        // the slice, not the whole space-padded field (red-dragon-zuhj).
        JsonObject operand = serializeMoveOperand(cls.getIdentifierCall());
        operand.addProperty("kind", "ref");
        obj.add("operand", operand);
    }

    /** Maps a ProLeap class-condition type to its canonical condition string, or null if unsupported. */
    private static String classConditionTypeToString(ClassCondition.ClassConditionType type) {
        if (type == null) {
            return null;
        }
        switch (type) {
            case NUMERIC:
                return "NUMERIC";
            case ALPHABETIC:
                return "ALPHABETIC";
            case ALPHABETIC_LOWER:
                return "ALPHABETIC-LOWER";
            case ALPHABETIC_UPPER:
                return "ALPHABETIC-UPPER";
            default:
                return null;
        }
    }

    /**
     * Populates {@code obj} for a SIGN relation condition (IF x IS POSITIVE /
     * NEGATIVE / ZERO), emitting the structured
     * {@code {"not": bool, "sign": "POSITIVE"|"NEGATIVE"|"ZERO", "operand": <expr>}}
     * shape — mirroring class conditions. The effective negation is the XOR of the
     * enclosing CombinableCondition's {@code not} and the sign condition's own
     * {@code not}. Falls back to the text path for this node only if unsupported.
     */
    private static void serializeSignCondition(JsonObject obj, SimpleCondition sc, boolean ccNot) {
        SignCondition sign = sc.getRelationCondition() != null
                ? sc.getRelationCondition().getSignCondition()
                : null;
        String signStr = sign != null ? signConditionTypeToString(sign.getSignConditionType()) : null;
        if (sign == null || signStr == null || sign.getArithmeticExpression() == null) {
            obj.addProperty("text", insertSpaces(sc.getCtx().getText()));
            return;
        }
        boolean effectiveNot = ccNot ^ sign.getNot();
        obj.addProperty("not", effectiveNot);
        obj.addProperty("sign", signStr);
        obj.add("operand", serializeArithmeticExpr(sign.getArithmeticExpression()));
    }

    /** Maps a ProLeap sign-condition type to its canonical string, or null if unsupported. */
    private static String signConditionTypeToString(SignCondition.SignConditionType type) {
        if (type == null) {
            return null;
        }
        switch (type) {
            case POSITIVE:
                return "POSITIVE";
            case NEGATIVE:
                return "NEGATIVE";
            case ZERO:
                return "ZERO";
            default:
                return null;
        }
    }

    /**
     * Serializes a RELATION_CONDITION to {"left": <expr>, "op": "...", "right": <expr>}.
     * Falls back to {"text": "..."} for SIGN and COMBINED condition types.
     */
    private static JsonObject serializeRelationCondition(RelationConditionValueStmt rel) {
        JsonObject obj = new JsonObject();
        if (rel.getRelationConditionType() == RelationConditionValueStmt.RelationConditionType.ARITHMETIC) {
            ArithmeticComparison ac = rel.getArithmeticComparison();
            if (ac != null) {
                obj.add("left", ac.getArithmeticExpressionLeft() != null
                        ? serializeArithmeticExpr(ac.getArithmeticExpressionLeft())
                        : litNode(""));
                obj.addProperty("op", relationalOpToString(ac.getOperator()));
                obj.add("right", ac.getArithmeticExpressionRight() != null
                        ? serializeArithmeticExpr(ac.getArithmeticExpressionRight())
                        : litNode(""));
                return obj;
            }
        }
        // SIGN — not yet structured; fall back to text (deferred).
        obj.addProperty("text", rel.getCtx() != null ? insertSpaces(rel.getCtx().getText()) : "");
        return obj;
    }

    /**
     * Serializes a COMBINED (abbreviated) relation into the incumbent AND/OR
     * condition tree, returning a full condition-node object (NOT a relation).
     *
     * <p>An abbreviated comparison {@code A = X OR Y} carries a single subject
     * {@code A} and operator {@code =}, with the trailing operands inheriting both.
     * Each operand becomes {@code {"not":false,"relation":{left:A,op:=,right:operand}}},
     * folded left into {@code {"op":"OR","left":...,"right":...}}.
     *
     * @return the condition node, or {@code null} if the shape is not a simple
     *         abbreviated comparison (caller should fall back to text).
     */
    private static JsonObject serializeCombinedComparison(CombinedComparison cc) {
        if (cc == null) {
            return null;
        }
        ArithmeticValueStmt subject = cc.getArithmeticExpression();
        CombinedCondition combined = cc.getCombinedCondition();
        if (subject == null || combined == null) {
            return null;
        }
        List<ArithmeticValueStmt> operands = combined.getArithmeticExpressions();
        if (operands == null || operands.isEmpty()) {
            return null;
        }
        String op = relationalOpToString(cc.getOperator());
        String boolOp = (combined.getCombinedConditionType()
                == CombinedCondition.CombinedConditionType.AND) ? "AND" : "OR";

        JsonElement subjectExpr = serializeArithmeticExpr(subject);
        JsonObject current = null;
        for (ArithmeticValueStmt operand : operands) {
            JsonObject relation = new JsonObject();
            relation.add("left", subjectExpr);
            relation.addProperty("op", op);
            relation.add("right", serializeArithmeticExpr(operand));

            JsonObject atom = new JsonObject();
            atom.addProperty("not", false);
            atom.add("relation", relation);

            if (current == null) {
                current = atom;
            } else {
                JsonObject compound = new JsonObject();
                compound.addProperty("op", boolOp);
                compound.add("left", current);
                compound.add("right", atom);
                current = compound;
            }
        }
        return current;
    }

    private static String relationalOpToString(RelationalOperator op) {
        if (op == null) return "==";
        switch (op.getRelationalOperatorType()) {
            case EQUAL: return "==";
            case GREATER: return ">";
            case GREATER_OR_EQUAL: return ">=";
            case LESS: return "<";
            case LESS_OR_EQUAL: return "<=";
            case NOT_EQUAL: return "!=";
            default: return "==";
        }
    }

    /**
     * Serializes an ArithmeticValueStmt as a left-folded expression tree.
     * Returns one of: {"kind":"ref","name":"..."}, {"kind":"lit","value":"..."},
     * {"kind":"binop","op":"...","left":<expr>,"right":<expr>},
     * {"kind":"neg","expr":<expr>}.
     */
    private static JsonElement serializeArithmeticExpr(ArithmeticValueStmt avs) {
        if (avs == null) return litNode("");
        JsonElement result = serializeMultDivs(avs.getMultDivs());
        for (PlusMinus pm : avs.getPlusMinus()) {
            JsonObject binop = new JsonObject();
            binop.addProperty("kind", "binop");
            binop.addProperty("op", pm.getPlusMinusType() == PlusMinus.PlusMinusType.PLUS ? "+" : "-");
            binop.add("left", result);
            binop.add("right", serializeMultDivs(pm.getMultDivs()));
            result = binop;
        }
        return result;
    }

    private static JsonElement serializeMultDivs(MultDivs md) {
        if (md == null) return litNode("");
        JsonElement result = serializePowers(md.getPowers());
        for (MultDiv mdo : md.getMultDivs()) {
            JsonObject binop = new JsonObject();
            binop.addProperty("kind", "binop");
            binop.addProperty("op", mdo.getMultDivType() == MultDiv.MultDivType.MULT ? "*" : "/");
            binop.add("left", result);
            binop.add("right", serializePowers(mdo.getPowers()));
            result = binop;
        }
        return result;
    }

    private static JsonElement serializePowers(Powers p) {
        if (p == null) return litNode("");
        // Exponentiation (**) is extremely rare in COBOL conditions; fall back to getText
        if (!p.getPowers().isEmpty()) {
            return litNode(p.getCtx() != null ? p.getCtx().getText() : "");
        }
        JsonElement base = serializeBasis(p.getBasis());
        if (p.getPowersType() == Powers.PowersType.MINUS) {
            JsonObject neg = new JsonObject();
            neg.addProperty("kind", "neg");
            neg.add("expr", base);
            return neg;
        }
        return base;
    }

    private static JsonElement serializeBasis(Basis b) {
        if (b == null) return litNode("");
        // Intrinsic FUNCTION call as a basis (e.g. inside an IF relation:
        // FUNCTION UPPER-CASE(A) = FUNCTION UPPER-CASE(B)). ProLeap surfaces the
        // basis as a CallValueStmt whose extractCallName collapses to just the
        // function NAME (dropping the call + args). Probe the basis's own grammar
        // subtree (self + descendants, NOT ancestors) for a functionCall rule and
        // emit the structured {"kind":"function","name":..,"args":[..]} node — the
        // same shape MOVE/arithmetic already produce (red-dragon-ge72).
        CobolParser.FunctionCallContext fnCtx =
                findFunctionCallCtxInSubtree(b.getCtx());
        if (fnCtx != null) {
            JsonObject fn = serializeFunctionNodeFromCtx(fnCtx);
            if (fn != null) {
                return fn;
            }
        }
        ValueStmt vs = b.getBasisValueStmt();
        if (vs instanceof CallValueStmt) {
            Call call = ((CallValueStmt) vs).getCall();
            JsonObject ref = new JsonObject();
            ref.addProperty("kind", "ref");
            if (call != null) {
                // Structured subscriptable reference (name + subscripts + ref-mod
                // + qualifiers). (red-dragon-6ddr)
                JsonObject struct = serializeRef(call);
                for (String key : struct.keySet()) {
                    ref.add(key, struct.get(key));
                }
            } else {
                ref.addProperty("name", b.getCtx().getText());
            }
            return ref;
        }
        if (vs instanceof ArithmeticValueStmt) {
            // Parenthesised sub-expression
            return serializeArithmeticExpr((ArithmeticValueStmt) vs);
        }
        if (vs instanceof LiteralValueStmt) {
            JsonObject dfh = serializeDfhrespLit((LiteralValueStmt) vs);
            if (dfh != null) return dfh;
            Literal lit = ((LiteralValueStmt) vs).getLiteral();
            if (lit != null && lit.getLiteralType() == Literal.LiteralType.FIGURATIVE_CONSTANT
                    && lit.getFigurativeConstant() != null) {
                String canonical = canonicalFigurative(lit.getFigurativeConstant().getFigurativeConstantType());
                if (canonical != null) {
                    JsonObject fig = new JsonObject();
                    fig.addProperty("kind", "figurative");
                    fig.addProperty("value", canonical);
                    return fig;
                }
            }
        }
        // Literals (LiteralValueStmt, IntegerLiteralValueStmt, etc.)
        String text = vs != null && vs.getCtx() != null ? vs.getCtx().getText()
                    : (b.getCtx() != null ? b.getCtx().getText() : "");
        return litNode(text);
    }

    /**
     * If {@code lvs} carries a {@code CICS_DFH_RESP} literal, returns a structured
     * {@code {"kind":"dfhresp","condition":"<NAME>"}} node; otherwise returns null.
     * Used by serializeBasis, serializeArithSource, serializeMove, and serializeEvaluate
     * so DFHRESP(X) is never emitted as a raw text string (red-dragon-kieo).
     */
    private static JsonObject serializeDfhrespLit(LiteralValueStmt lvs) {
        if (lvs == null) return null;
        Literal lit = lvs.getLiteral();
        if (lit == null || lit.getLiteralType() != Literal.LiteralType.CICS_DFH_RESP) return null;
        if (!(lit.getCtx() instanceof CobolParser.LiteralContext)) return null;
        CobolParser.CicsDfhRespLiteralContext dfhCtx =
            ((CobolParser.LiteralContext) lit.getCtx()).cicsDfhRespLiteral();
        String cond = (dfhCtx != null && dfhCtx.cobolWord() != null)
            ? dfhCtx.cobolWord().getText().toUpperCase() : "";
        JsonObject obj = new JsonObject();
        obj.addProperty("kind", "dfhresp");
        obj.addProperty("condition", cond);
        return obj;
    }

    /**
     * Emit a dfhresp node when vs is a LiteralValueStmt with CICS_DFH_RESP type.
     *
     * With the grammar fix (literal before identifier in basis and evaluateValue),
     * DFHRESP(X) always parses as LiteralValueStmt in every context (red-dragon-kieo).
     * Returns null when vs is not a DFHRESP literal.
     */
    private static JsonObject serializeDfhrespFromVS(ValueStmt vs) {
        if (vs instanceof LiteralValueStmt) {
            return serializeDfhrespLit((LiteralValueStmt) vs);
        }
        return null;
    }

    // ── Grammar-context arithmetic serializers (for referenceModifier) ──────────

    /**
     * Grammar: arithmeticExpression : multDivs plusMinus*
     * plusMinus : (PLUSCHAR | MINUSCHAR) multDivs
     * Note: ctx.multDivs() is SINGULAR (not a list); ctx.plusMinus() is a List.
     */
    private static JsonElement serializeArithExprCtx(CobolParser.ArithmeticExpressionContext ctx) {
        if (ctx == null) return litNode("");
        JsonElement result = serializeMultDivsCtx(ctx.multDivs());
        for (CobolParser.PlusMinusContext pm : ctx.plusMinus()) {
            JsonObject binop = new JsonObject();
            binop.addProperty("kind", "binop");
            binop.addProperty("op", pm.PLUSCHAR() != null ? "+" : "-");
            binop.add("left", result);
            binop.add("right", serializeMultDivsCtx(pm.multDivs()));
            result = binop;
        }
        return result;
    }

    /**
     * Grammar: multDivs : powers multDiv*
     * multDiv : (ASTERISKCHAR | SLASHCHAR) powers
     * Note: ctx.powers() is SINGULAR; ctx.multDiv() is a List.
     */
    private static JsonElement serializeMultDivsCtx(CobolParser.MultDivsContext ctx) {
        if (ctx == null) return litNode("");
        JsonElement result = serializePowersCtx(ctx.powers());
        for (CobolParser.MultDivContext md : ctx.multDiv()) {
            JsonObject binop = new JsonObject();
            binop.addProperty("kind", "binop");
            binop.addProperty("op", md.ASTERISKCHAR() != null ? "*" : "/");
            binop.add("left", result);
            binop.add("right", serializePowersCtx(md.powers()));
            result = binop;
        }
        return result;
    }

    /**
     * Grammar: powers : (PLUSCHAR | MINUSCHAR)? basis power*
     * power : DOUBLEASTERISKCHAR basis
     * Note: ctx.basis() is SINGULAR; ctx.power() is a List.
     */
    private static JsonElement serializePowersCtx(CobolParser.PowersContext ctx) {
        if (ctx == null) return litNode("");
        JsonElement result = serializeBasisCtx(ctx.basis());
        for (CobolParser.PowerContext p : ctx.power()) {
            JsonObject binop = new JsonObject();
            binop.addProperty("kind", "binop");
            binop.addProperty("op", "**");
            binop.add("left", result);
            binop.add("right", serializeBasisCtx(p.basis()));
            result = binop;
        }
        if (ctx.MINUSCHAR() != null) {
            JsonObject neg = new JsonObject();
            neg.addProperty("kind", "neg");
            neg.add("expr", result);
            return neg;
        }
        return result;
    }

    /**
     * Returns the LEAF data-name of an identifier, dropping OF/IN qualification.
     *
     * COBOL `FLD-A OF GRP-B` is one field named the qualified way; red-dragon
     * resolves data items by leaf name, so we emit "FLD-A" (the first dataName of
     * qualifiedDataNameFormat1) rather than the flattened parse-tree text
     * "FLD-AOFGRP-B" that getText() would produce. Falls back to getText() for
     * non-qualifiedDataName identifiers (tableCall / functionCall / specialRegister).
     */
    /**
     * If the EVALUATE select ValueStmt is a QUALIFIED data name (carries an
     * {@code OF}/{@code IN} qualifier), returns its LEAF data name; otherwise
     * returns {@code null} so the caller keeps the existing flat-text subject.
     * The leaf alone resolves the field here because the qualified subject names
     * a unique field (CardDemo COTRN02C: {@code CONFIRMI OF COTRN2AI}). Structural
     * — walks the parse tree, no text parsing. (red-dragon)
     */
    private static String qualifiedSubjectLeaf(ValueStmt vs) {
        if (vs == null) {
            return null;
        }
        ParserRuleContext ctx;
        try {
            ctx = vs.getCtx();
        } catch (Exception e) {
            return null;
        }
        if (ctx == null) {
            return null;
        }
        // Only rewrite when an OF/IN qualifier is actually present, so simple
        // subjects keep their existing serialization untouched.
        JsonArray quals = new JsonArray();
        collectInDataQualifiers(ctx, quals);
        if (quals.size() == 0) {
            return null;
        }
        CobolParser.QualifiedDataNameFormat1Context f1 =
                findQualifiedDataNameFormat1(ctx);
        if (f1 != null && f1.dataName() != null) {
            return f1.dataName().getText();
        }
        return null;
    }

    private static CobolParser.QualifiedDataNameFormat1Context
            findQualifiedDataNameFormat1(org.antlr.v4.runtime.tree.ParseTree node) {
        if (node == null) {
            return null;
        }
        if (node instanceof CobolParser.QualifiedDataNameFormat1Context) {
            return (CobolParser.QualifiedDataNameFormat1Context) node;
        }
        for (int i = 0; i < node.getChildCount(); i++) {
            CobolParser.QualifiedDataNameFormat1Context found =
                    findQualifiedDataNameFormat1(node.getChild(i));
            if (found != null) {
                return found;
            }
        }
        return null;
    }

    private static String leafDataName(CobolParser.IdentifierContext id) {
        if (id == null) {
            return "";
        }
        CobolParser.QualifiedDataNameContext qdn = id.qualifiedDataName();
        if (qdn != null) {
            CobolParser.QualifiedDataNameFormat1Context f1 = qdn.qualifiedDataNameFormat1();
            if (f1 != null && f1.dataName() != null) {
                return f1.dataName().getText();
            }
        }
        return id.getText();
    }

    /**
     * Bare base data-name of an identifier, with any reference-modifier suffix
     * stripped. {@link #leafDataName} falls back to {@code id.getText()} when the
     * qualifiedDataName carries a referenceModifier (its {@code dataName()} is then
     * null), which would glue the {@code (start:len)} slice into the name — an
     * unresolvable field. This searches structurally for the underlying
     * qualifiedDataNameFormat1's dataName instead. (red-dragon-74qu)
     */
    private static String baseDataName(CobolParser.IdentifierContext id) {
        if (id == null) {
            return "";
        }
        CobolParser.QualifiedDataNameFormat1Context f1 = findQualifiedDataNameFormat1(id);
        if (f1 != null && f1.dataName() != null) {
            return f1.dataName().getText();
        }
        return leafDataName(id);
    }

    /**
     * Serializes an identifier that MAY carry a reference modifier into a
     * structured ref node: {@code {kind:ref, name:<bare base>, ref_mod_start,
     * ref_mod_length?}}. Mirrors {@link #serializeRef}'s ref-mod handling for the
     * grammar-context paths (function args, arithmetic basis) that operate on an
     * IdentifierContext rather than a Call. Returns {@code null} when the
     * identifier carries no reference modifier (caller emits a plain ref).
     * (red-dragon-74qu)
     */
    private static JsonObject serializeRefModIdentifier(CobolParser.IdentifierContext id) {
        if (id == null) {
            return null;
        }
        CobolParser.ReferenceModifierContext refMod = firstReferenceModifierDescendant(id);
        if (refMod == null) {
            return null;
        }
        JsonObject ref = new JsonObject();
        ref.addProperty("kind", "ref");
        ref.addProperty("name", baseDataName(id));
        JsonObject rm = serializeRefMod(refMod);
        ref.add("ref_mod_start", rm.get("ref_mod_start"));
        if (rm.has("ref_mod_length")) {
            ref.add("ref_mod_length", rm.get("ref_mod_length"));
        }
        return ref;
    }

    /**
     * Grammar: basis : LPARENCHAR arithmeticExpression RPARENCHAR | identifier | literal
     * Note: ctx.arithmeticExpression() is non-null for parenthesised sub-expressions.
     */
    private static JsonElement serializeBasisCtx(CobolParser.BasisContext ctx) {
        if (ctx == null) return litNode("");
        if (ctx.arithmeticExpression() != null) {
            return serializeArithExprCtx(ctx.arithmeticExpression());
        }
        CobolParser.IdentifierContext id = ctx.identifier();
        // Nested intrinsic FUNCTION as a basis (e.g. FUNCTION UPPER-CASE(FUNCTION
        // TRIM(x))). ProLeap surfaces the inner function as an identifier whose
        // subtree holds the functionCall rule; without this probe it serializes
        // as the bare function NAME ref ("TRIM"). Emit the structured function
        // node so the call + args survive (red-dragon-ge72).
        CobolParser.FunctionCallContext fnCtx = findFunctionCallCtxInSubtree(id);
        if (fnCtx != null) {
            JsonObject fn = serializeFunctionNodeFromCtx(fnCtx);
            if (fn != null) {
                return fn;
            }
        }
        if (id != null) {
            // LENGTH OF <field> surfaces as an identifier wrapping a
            // specialRegister; getText() would glue it into "LENGTHOF<field>"
            // (an unresolvable name the frontend treats as 0). Emit a structured
            // length_of node so the frontend resolves the field's byte length —
            // matching serializeFromValue's PERFORM-VARYING handling. (oq2c)
            CobolParser.SpecialRegisterContext sr = findLengthOfSpecialRegister(id);
            if (sr != null) {
                JsonObject obj = new JsonObject();
                obj.addProperty("kind", "length_of");
                CobolParser.IdentifierContext inner = sr.identifier();
                obj.addProperty("name", inner != null ? leafDataName(inner) : "");
                return obj;
            }
            // A reference-modified identifier (e.g. WS-FLD(1:LEN)) must keep its
            // slice structured so the frontend resolves the base field and the
            // start/length, rather than gluing them into an unresolvable name.
            // (red-dragon-74qu)
            JsonObject refMod = serializeRefModIdentifier(id);
            if (refMod != null) {
                return refMod;
            }
            JsonObject ref = new JsonObject();
            ref.addProperty("kind", "ref");
            ref.addProperty("name", leafDataName(id));
            return ref;
        }
        CobolParser.LiteralContext lit = ctx.literal();
        if (lit != null && lit.figurativeConstant() != null) {
            String canonical = canonicalFigurativeCtx(lit.figurativeConstant());
            if (canonical != null) {
                JsonObject fig = new JsonObject();
                fig.addProperty("kind", "figurative");
                fig.addProperty("value", canonical);
                return fig;
            }
        }
        return litNode(lit != null ? lit.getText() : "");
    }

    /**
     * Maps a figurative-constant grammar context to the canonical comparison string.
     * Mirrors {@link #canonicalFigurative} but reads ANTLR terminal nodes directly,
     * for the grammar-context fallback path used on abbreviated conditions.
     */
    private static String canonicalFigurativeCtx(CobolParser.FigurativeConstantContext fc) {
        if (fc == null) return null;
        if (fc.SPACE() != null || fc.SPACES() != null) return "SPACES";
        if (fc.ZERO() != null || fc.ZEROS() != null || fc.ZEROES() != null) return "ZEROS";
        if (fc.LOW_VALUE() != null || fc.LOW_VALUES() != null) return "LOW-VALUES";
        if (fc.HIGH_VALUE() != null || fc.HIGH_VALUES() != null) return "HIGH-VALUES";
        if (fc.QUOTE() != null || fc.QUOTES() != null) return "QUOTES";
        return null;
    }

    private static JsonObject litNode(String value) {
        JsonObject lit = new JsonObject();
        lit.addProperty("kind", "lit");
        lit.addProperty("value", value);
        return lit;
    }

    /**
     * Maps a ProLeap figurative-constant type to the canonical string the Python
     * condition lowering recognises. Returns {@code null} for figuratives without
     * a meaningful comparison fill (e.g. ALL/NULL) so callers fall back to text.
     */
    private static String canonicalFigurative(FigurativeConstant.FigurativeConstantType type) {
        if (type == null) return null;
        switch (type) {
            case SPACE:
            case SPACES:
                return "SPACES";
            case ZERO:
            case ZEROS:
            case ZEROES:
                return "ZEROS";
            case LOW_VALUE:
            case LOW_VALUES:
                return "LOW-VALUES";
            case HIGH_VALUE:
            case HIGH_VALUES:
                return "HIGH-VALUES";
            case QUOTE:
            case QUOTES:
                return "QUOTES";
            default:
                return null;
        }
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
