from datetime import datetime
from decimal import Decimal, InvalidOperation

from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cashflows.models import CashFlowItem
from apps.forecasts.alerts import generate_alerts
from apps.forecasts.engine import build_monthly_buckets
from apps.forecasts.liquidity import compute_liquidity
from apps.forecasts.scenarios import EXPECTED

from .context import build_financial_context
from .gemini_client import ask_gemini


class ChatView(APIView):
    def post(self, request):
        question = (request.data.get("question") or "").strip()
        if not question:
            return Response({"detail": "question is required"}, status=400)

        scenario = request.data.get("scenario", EXPECTED)
        horizon = int(request.data.get("horizon", 12))
        context = build_financial_context(request.user, horizon_months=horizon, scenario=scenario)
        answer = ask_gemini(question, context)
        return Response({"answer": answer})


class WhatIfView(APIView):
    def post(self, request):
        data = request.data
        kind = data.get("kind", CashFlowItem.Kind.WITHDRAWAL)
        amount = data.get("amount")
        start_date = data.get("date")
        name = data.get("name", "What-if scenario item")

        if amount is None or not start_date:
            return Response({"detail": "amount and date are required"}, status=400)

        if kind not in CashFlowItem.Kind.values:
            return Response({"detail": "invalid kind"}, status=400)

        try:
            parsed_amount = Decimal(str(amount))
        except InvalidOperation:
            return Response({"detail": "amount must be a number"}, status=400)

        try:
            parsed_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        except ValueError:
            return Response({"detail": "date must be YYYY-MM-DD"}, status=400)

        extra_item = CashFlowItem(
            user=request.user,
            kind=kind,
            name=name,
            amount=parsed_amount,
            start_date=parsed_date,
            frequency=CashFlowItem.Frequency.ONE_TIME,
        )

        horizon = int(data.get("horizon", 12))
        scenario = data.get("scenario", EXPECTED)

        baseline = build_monthly_buckets(request.user, horizon_months=horizon, scenario=scenario)
        adjusted = build_monthly_buckets(request.user, horizon_months=horizon, scenario=scenario, extra_item=extra_item)

        context = build_financial_context(request.user, horizon_months=horizon, scenario=scenario, extra_item=extra_item)
        question = (
            f"What happens to my liquidity if I have a {kind} of {amount} on {start_date}? "
            "Explain the impact in 2-3 sentences."
        )
        explanation = ask_gemini(question, context)

        return Response({
            "baseline": baseline,
            "adjusted": adjusted,
            "liquidity": compute_liquidity(request.user),
            "alerts": generate_alerts(request.user, adjusted),
            "explanation": explanation,
        })
