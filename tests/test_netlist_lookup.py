from __future__ import annotations

import pytest

from altium_monkey import AmbiguousNetNameError
from altium_monkey.altium_netlist_model import Net, Netlist


def test_netlist_lookup_distinguishes_canonical_names_from_provenance_aliases() -> None:
    canonical = Net(name="VIN", aliases=[])
    first_channel = Net(name="VIN.1", aliases=["VIN_LOCAL"])
    second_channel = Net(name="VIN.2", aliases=["VIN_LOCAL", "J2_PIN_2"])
    netlist = Netlist(nets=[canonical, first_channel, second_channel])

    assert netlist.resolve_net("VIN") is canonical
    assert netlist.resolve_net("J2_PIN_2") is second_channel
    assert netlist.resolve_net("MISSING") is None
    assert netlist.get_nets_by_alias("VIN_LOCAL") == [first_channel, second_channel]

    with pytest.raises(AmbiguousNetNameError) as exc_info:
        netlist.resolve_net("VIN_LOCAL")

    assert exc_info.value.name == "VIN_LOCAL"
    assert exc_info.value.candidate_names == ["VIN.1", "VIN.2"]
