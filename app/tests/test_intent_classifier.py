# app/tests/test_intent_classifier.py
import unittest
import asyncio
from app.services.intent_classifier import classify_intent

class TestIntentClassifier(unittest.TestCase):
    def test_classify_intent_greetings(self):
        res = asyncio.run(classify_intent("hello"))
        self.assertEqual(res["category"], "Casual Chat")
        self.assertEqual(res["confidence"], 1.0)
