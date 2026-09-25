"""Compact exported-repository test of axpe's post-fabrication loader."""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles


async def ticks(dut, count):
    await ClockCycles(dut.clk, count)


async def drive(dut, *, sclk=0, mosi=0, cs_n=1):
    dut.ui_in.value = sclk | (mosi << 1) | (cs_n << 2)
    await ticks(dut, 4)


async def transfer(dut, value, bits):
    received = 0
    for bit in range(bits - 1, -1, -1):
        await drive(dut, sclk=0, mosi=(value >> bit) & 1, cs_n=0)
        received = (received << 1) | (int(dut.uo_out.value) & 1)
        await drive(dut, sclk=1, mosi=(value >> bit) & 1, cs_n=0)
    await drive(dut, sclk=0, cs_n=0)
    return received


async def write_word(dut, address, value):
    await drive(dut, cs_n=0)
    await transfer(dut, 0x01, 8)
    await transfer(dut, address, 8)
    await transfer(dut, value, 32)
    await drive(dut, cs_n=1)


async def read_word(dut, address):
    await drive(dut, cs_n=0)
    await transfer(dut, 0x02, 8)
    await transfer(dut, address, 8)
    value = await transfer(dut, 0, 32)
    await drive(dut, cs_n=1)
    return value


@cocotb.test()
async def loader_reprograms_one_design(dut):
    cocotb.start_soon(Clock(dut.clk, 20, unit="ns").start())
    dut.ena.value = 1
    dut.ui_in.value = 4
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ticks(dut, 8)
    dut.rst_n.value = 1
    await ticks(dut, 8)

    first = 0x12345678
    second = 0xA5C30F69
    await write_word(dut, 7, first)
    assert await read_word(dut, 7) == first
    await write_word(dut, 7, second)
    assert await read_word(dut, 7) == second
