import unittest

from engteacher.card_deck import CardDeck


def _records(*ids: int) -> list[dict]:
    return [{"id": i} for i in ids]


class CardDeckTest(unittest.TestCase):
    def test_empty_deck_has_no_card(self):
        deck = CardDeck()
        self.assertIsNone(deck.current())
        self.assertEqual((deck.position(), len(deck)), (0, 0))
        self.assertTrue(deck.is_at_oldest())
        self.assertTrue(deck.is_at_newest())
        self.assertFalse(deck.older())
        self.assertFalse(deck.newer())
        self.assertFalse(deck.newest())

    def test_first_add_shows_newest(self):
        deck = CardDeck()
        self.assertTrue(deck.add(_records(1, 2, 3)))
        self.assertEqual(deck.current(), {"id": 3})
        self.assertEqual((deck.position(), len(deck)), (3, 3))

    def test_add_nothing_changes_nothing(self):
        deck = CardDeck()
        deck.add(_records(1))
        self.assertFalse(deck.add([]))
        self.assertEqual(deck.current(), {"id": 1})

    def test_moves_stop_at_both_ends(self):
        deck = CardDeck()
        deck.add(_records(1, 2))
        self.assertFalse(deck.newer())
        self.assertTrue(deck.older())
        self.assertEqual(deck.current(), {"id": 1})
        self.assertTrue(deck.is_at_oldest())
        self.assertFalse(deck.older())
        self.assertTrue(deck.newer())
        self.assertEqual(deck.current(), {"id": 2})

    def test_new_records_follow_when_at_newest(self):
        deck = CardDeck()
        deck.add(_records(1))
        self.assertTrue(deck.add(_records(2, 3)))
        self.assertEqual(deck.current(), {"id": 3})

    def test_new_records_keep_place_when_reading_older(self):
        deck = CardDeck()
        deck.add(_records(1, 2))
        deck.older()
        self.assertFalse(deck.add(_records(3)))
        self.assertEqual(deck.current(), {"id": 1})
        self.assertEqual((deck.position(), len(deck)), (1, 3))
        self.assertTrue(deck.newest())
        self.assertEqual(deck.current(), {"id": 3})
        self.assertFalse(deck.newest())

    def test_move_to_index(self):
        deck = CardDeck()
        deck.add(_records(1, 2, 3))
        self.assertTrue(deck.move_to(0))
        self.assertEqual(deck.current(), {"id": 1})
        self.assertFalse(deck.move_to(0))
        self.assertFalse(deck.move_to(3))
        self.assertFalse(deck.move_to(-1))
        self.assertEqual(deck.current(), {"id": 1})


if __name__ == "__main__":
    unittest.main()
