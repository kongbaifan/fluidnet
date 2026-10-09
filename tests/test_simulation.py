import copy

import pytest

from fluidnet.errors import ModelError
from fluidnet.examples import controlled, tanks
from fluidnet.media import MediumRegistry
from fluidnet.models import MediumDefinition
from fluidnet.simulation import SimulationSession


def test_property_enthalpy_round_trip():
    water = MediumRegistry([MediumDefinition()]).get("water")
    for temperature in [280, 293.15, 333.15, 360]:
        state = water.state_pt(301325, temperature)
        back = water.state_ph(301325, state.enthalpy_j_kg)
        assert back.temperature_k == pytest.approx(temperature, abs=1e-7)
        assert back.enthalpy_j_kg == pytest.approx(state.enthalpy_j_kg, abs=1e-5)


def test_tank_mass_and_energy_conservation():
    session = SimulationSession(tanks(), 0.1)
    mass0, energy0 = session.inventory()
    level0 = session.frame["elements"]["tank_a"]["level_m"]
    for _ in range(10):
        session.step()
    mass1, energy1 = session.inventory()
    assert mass1 == pytest.approx(mass0, rel=1e-8)
    assert energy1 == pytest.approx(energy0, rel=1e-7)
    assert session.frame["elements"]["tank_a"]["level_m"] < level0
    assert session.time_s == pytest.approx(1.0)
    assert session.status == "paused"


def test_geometry_change_does_not_mutate_running_model():
    session = SimulationSession(tanks())
    before = session.net.parameters["pipe"]["length_m"]
    with pytest.raises(ModelError):
        session.set_parameter("pipe", "length_m", 100)
    assert session.net.parameters["pipe"]["length_m"] == before
    session.set_parameter("valve", "opening", 0.3)
    assert session.events[-1]["time_s"] == 0


def test_pid_is_deterministic_and_bounded():
    a = SimulationSession(controlled(), 0.1)
    b = SimulationSession(controlled(), 0.1)
    for _ in range(5):
        fa, fb = a.step(), b.step()
        assert fa["elements"]["trunk"]["mass_flow_kg_s"] == pytest.approx(fb["elements"]["trunk"]["mass_flow_kg_s"], rel=1e-10)
        assert 0.2 <= fa["elements"]["controller"]["output"] <= 1.3


def test_smaller_timestep_converges_to_same_tank_result():
    a, b = SimulationSession(tanks(), 0.2), SimulationSession(tanks(), 0.1)
    for _ in range(5):
        a.step()
        b.step(); b.step()
    assert a.frame["elements"]["tank_b"]["temperature_k"] == pytest.approx(b.frame["elements"]["tank_b"]["temperature_k"], abs=0.01)
