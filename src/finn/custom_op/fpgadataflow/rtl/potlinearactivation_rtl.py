# Copyright (C) 2024, Advanced Micro Devices, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
#
# * Neither the name of FINN nor the names of its
#   contributors may be used to endorse or promote products derived from
#   this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import numpy as np
import os
import shutil
from bitstring import BitArray, Bits
from pyverilator.util.axi_utils import reset_rtlsim, rtlsim_multi_io
from qonnx.core.datatype import DataType

from finn.custom_op.fpgadataflow.potlinearactivation import POTLinearActivation
from finn.custom_op.fpgadataflow.rtlbackend import RTLBackend
from finn.util.basic import get_rtlsim_trace_depth, make_build_dir
from finn.util.data_packing import npy_to_rtlsim_input, rtlsim_output_to_npy

try:
    from pyverilator import PyVerilator
except ModuleNotFoundError:
    PyVerilator = None


class POTLinearActivation_rtl(POTLinearActivation, RTLBackend):
    """Class that corresponds to finn-rtllib 'pot_linear' function."""

    def __init__(self, onnx_node, **kwargs):
        super().__init__(onnx_node, **kwargs)

    def get_nodeattr_types(self):
        my_attrs = {}
        my_attrs.update(POTLinearActivation.get_nodeattr_types(self))
        my_attrs.update(RTLBackend.get_nodeattr_types(self))
        return my_attrs

    def get_pe_mem_geometries(self):
        """return a list of (bitwidth, depth) for PE memory configurations to be used
        in resource estimation

        for each bitwidth, the depth is calculated as the
        number of thresholds that can be stored in a single
        memory block
        the bitwidth is the bitwidth of the threshold values
        the depth is the number of thresholds that can be stored
        in a single memory block
        the number of memory blocks is calculated as the number
        of thresholds divided by the depth
        the number of memory blocks is then multiplied by the
        number of PEs to get the total number of memory blocks
        required for the entire layer
        """
        # pe = self.get_nodeattr("PE")
        # wdt = self.get_weight_datatype()
        # wdt_bits = wdt.bitwidth()
        # odt = self.get_output_datatype()
        # odt_bits = odt.bitwidth()
        # t_channels = self.get_nodeattr("NumChannels")
        # cf = t_channels / pe
        # is_uniform = self.get_nodeattr("uniform_thres")
        # if is_uniform:
        #     ret = [(odt_bits - x, cf * (2**x)) for x in range(1, odt_bits)]
        # else:
        #     ret = [(wdt_bits, (cf) * 2**x) for x in range(odt_bits)]
        # return ret

    def get_memory_estimate(self):
        """return the memory estimate for this node"""
        res_dict = {}
        return res_dict

    def bram_estimation(self):
        """return the number of BRAMs required for this node"""
        res_dict = self.get_memory_estimate()
        return res_dict.get("BRAM", 0)

    def uram_estimation(self):
        """return the number of URAMs required for this node"""
        res_dict = self.get_memory_estimate()
        return res_dict.get("URAM", 0)

    def lut_estimation(self):
        """return the number of LUTs required for this node"""
        res_dict = self.get_memory_estimate()
        return res_dict.get("LUTRAM", 0)

    def get_exp_cycles(self):
        return self.get_number_output_values() + 2

    def generate_hdl(self, model, fpgapart, clk):
        """Prepare HDL files from templates for synthesis"""
        rtlsrc = os.environ["FINN_ROOT"] + "/finn-rtllib/potlinear"
        template_path = rtlsrc + "/pot_linear_wrapper.sv"

        topname = self.get_verilog_top_module_name()
        self.set_nodeattr("gen_top_module", topname)

        idt = self.get_input_datatype()
        odt = self.get_output_datatype()
        bdt = self.get_biases_datatype()

        shifts = model.get_initializer(self.onnx_node.input[1])
        biases = model.get_initializer(self.onnx_node.input[2])
        shifts_unique = np.unique(shifts)
        shift_bits = int(np.ceil(np.log2(len(shifts_unique))))
        shift_dict = {s: i for i, s in enumerate(shifts_unique)}
        new_shifts = np.asarray([shift_dict[s] for s in shifts])

        # Generate a dictionary of values to put in RTL template
        code_gen_dict = {}
        code_gen_dict["$TOPMODULE$"] = topname
        code_gen_dict["$IBITS$"] = str(idt.bitwidth())
        code_gen_dict["$OBITS$"] = str(odt.bitwidth())
        code_gen_dict["$BBITS$"] = str(bdt.bitwidth())
        code_gen_dict["$PE$"] = self.get_nodeattr("PE")
        code_gen_dict["$FOLD$"] = str(self.get_nodeattr("NumChannels") // self.get_nodeattr("PE"))
        code_gen_dict["$N_SHIFTS$"] = str(len(shifts_unique))
        code_gen_dict["$SHIFTS$"] = ", ".join(str(s) for s in shifts_unique)
        code_gen_dict["$ISIGNED$"] = "1" if idt.signed() else "0"
        code_gen_dict["$OSIGNED$"] = "1" if odt.signed() else "0"
        code_gen_dict["$RAM_STYLE$"] = "block"

        # Retrieve the destination directory for the final RTL files
        code_gen_dir = self.get_nodeattr("code_gen_dir_ipgen")
        with open(template_path, "r") as f:
            template = f.read()
        for key_name in code_gen_dict:
            key = "%s" % key_name
            template = template.replace(key, str(code_gen_dict[key_name]))
        with open(
            os.path.join(code_gen_dir, self.get_verilog_top_module_name() + ".sv"),
            "w",
        ) as f:
            f.write(template)

        shutil.copy(rtlsrc + "/pot_linear.sv", code_gen_dir)

        memfile = code_gen_dir + "/memdata.dat"
        pe = self.get_nodeattr("PE")
        new_shifts = new_shifts.reshape((-1, pe))
        biases = biases.reshape((-1, pe))

        def convert_slice(shift, bias):
            slice = BitArray()
            for s, b in zip(shift, bias):
                slice.prepend(Bits(int=b, length=bdt.bitwidth()))
                slice.prepend(Bits(uint=s, length=shift_bits))
            pad = -len(slice) % 4
            if pad > 0:
                slice.prepend(Bits(int=0, length=pad))
            return slice.hex

        mem = [convert_slice(shift, bias) for shift, bias in zip(new_shifts, biases)]
        with open(memfile, "w") as f:
            f.write("\n".join(mem))
            f.write("\n")

        return

    def prepare_rtlsim(self):
        """Creates a Verilator emulation library for the RTL code generated
        for this node, sets the rtlsim_so attribute to its path and returns
        a PyVerilator wrapper around it."""

        if PyVerilator is None:
            raise ImportError("Installation of PyVerilator is required.")

        code_gen_dir = self.get_nodeattr("code_gen_dir_ipgen")
        verilog_paths = [code_gen_dir]
        verilog_files = [self.get_nodeattr("gen_top_module") + ".sv", "pot_linear.sv"]
        single_src_dir = make_build_dir("pyverilator_" + self.onnx_node.name + "_")
        shutil.copy(code_gen_dir + "/memdata.dat", single_src_dir)

        # build the Verilator emulation library
        sim = PyVerilator.build(
            verilog_files,
            build_dir=single_src_dir,
            verilog_path=verilog_paths,
            trace_depth=get_rtlsim_trace_depth(),
            top_module_name=self.get_nodeattr("gen_top_module"),
            auto_eval=False,
        )

        # save generated lib filename in attribute
        self.set_nodeattr("rtlsim_so", sim.lib._name)
        return sim

    def execute_node(self, context, graph):
        mode = self.get_nodeattr("exec_mode")
        code_gen_dir = self.get_nodeattr("code_gen_dir_ipgen")
        if mode == "cppsim":
            POTLinearActivation.execute_node(self, context, graph)
        elif mode == "rtlsim":
            node = self.onnx_node
            # create a npy file for each input of the node (in_ind is input index)
            for in_ind, inputs in enumerate(node.input):
                # it is assumed that the first input of the node is the data input
                if in_ind == 0:
                    assert (
                        str(context[inputs].dtype) == "float32"
                    ), """Input datatype is
                    not float32 as expected."""
                    expected_inp_shape = self.get_folded_input_shape()
                    reshaped_input = context[inputs].reshape(expected_inp_shape)

                    if self.get_input_datatype() == DataType["BIPOLAR"]:
                        # store bipolar activations as binary
                        reshaped_input = (reshaped_input + 1) / 2
                        export_idt = DataType["BINARY"]
                    else:
                        export_idt = self.get_input_datatype()

                    # make copy before saving the array
                    reshaped_input = reshaped_input.copy()
                    np.save(
                        os.path.join(code_gen_dir, "input_{}.npy".format(in_ind)),
                        reshaped_input,
                    )
                elif in_ind > 3:
                    raise Exception("Unexpected input found for Thresholding_rtl")

            # Create a PyVerilator wrapper of the RTLSim .so
            sim = self.get_rtlsim()
            nbits = self.get_instream_width()
            inp = npy_to_rtlsim_input("{}/input_0.npy".format(code_gen_dir), export_idt, nbits)
            io_names = self.get_verilog_top_module_intf_names()
            istream_name = io_names["s_axis"][0][0]
            ostream_name = io_names["m_axis"][0][0]
            io_dict = {
                "inputs": {istream_name: inp},
                "outputs": {ostream_name: []},
            }

            trace_file = self.get_nodeattr("rtlsim_trace")
            if trace_file == "default":
                trace_file = self.onnx_node.name + ".vcd"
            sname = "_"

            # Change into so directory to ensure threshold files can be found
            rtlsim_so = self.get_nodeattr("rtlsim_so")
            so_dir = os.path.dirname(os.path.realpath(rtlsim_so))
            olcwd = os.getcwd()
            os.chdir(so_dir)
            num_out_values = self.get_number_output_values()
            reset_rtlsim(sim)
            total_cycle_count = rtlsim_multi_io(
                sim,
                io_dict,
                num_out_values,
                trace_file=trace_file,
                sname=sname,
                liveness_threshold=self.get_exp_cycles() + 10,
            )
            self.set_nodeattr("cycles_rtlsim", total_cycle_count)
            os.chdir(olcwd)
            output = io_dict["outputs"][ostream_name]

            # Manage output data
            odt = self.get_output_datatype()
            target_bits = odt.bitwidth()
            packed_bits = self.get_outstream_width()
            out_npy_path = "{}/output.npy".format(code_gen_dir)
            out_shape = self.get_folded_output_shape()

            rtlsim_output_to_npy(output, out_npy_path, odt, out_shape, packed_bits, target_bits)

            # load and reshape output
            output = np.load(out_npy_path)
            oshape = self.get_normal_output_shape()
            output = np.asarray([output], dtype=np.float32).reshape(*oshape)
            context[node.output[0]] = output
        else:
            raise Exception(
                """Invalid value for attribute exec_mode! Is currently set to: {}
            has to be set to one of the following value ("cppsim", "rtlsim")""".format(
                    mode
                )
            )
