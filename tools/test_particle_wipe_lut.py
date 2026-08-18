"""LUT particle wipe must match the loop reference bitwise."""

from __future__ import annotations

import numpy as np

from src.core.preprocessing import BinaryPostProcessor


def test_lut_matches_loop_on_random_speckle():
    rng = np.random.default_rng(0)
    noise = (rng.random((128, 128)) > 0.92).astype(np.uint8) * 255
    ref = BinaryPostProcessor.remove_small_particles_improved_ref(noise)
    lut = BinaryPostProcessor.remove_small_particles_improved(noise)
    assert np.array_equal(ref, lut)


def test_lut_matches_loop_on_empty():
    empty = np.zeros((64, 64), dtype=np.uint8)
    ref = BinaryPostProcessor.remove_small_particles_improved_ref(empty)
    lut = BinaryPostProcessor.remove_small_particles_improved(empty)
    assert np.array_equal(ref, lut)


def test_lut_none_passthrough():
    assert BinaryPostProcessor.remove_small_particles_improved(None) is None
    assert BinaryPostProcessor.remove_small_particles_improved_ref(None) is None
