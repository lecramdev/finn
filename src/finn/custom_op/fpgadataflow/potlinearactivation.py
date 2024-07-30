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
import warnings
from qonnx.core.datatype import DataType

from finn.custom_op.fpgadataflow.hwcustomop import HWCustomOp


class POTLinearActivation(HWCustomOp):
    """Abstraction layer for HW implementation of Thresholding."""

    def __init__(self, onnx_node, **kwargs):
        super().__init__(onnx_node, **kwargs)

    def get_nodeattr_types(self):
        my_attrs = {
            # parallelization; channels per cycle
            "PE": ("i", True, 0),
            # number of channels
            "NumChannels": ("i", True, 0),
            # FINN DataTypes for inputs, outputs
            "inputDataType": ("s", True, ""),
            "shiftsDataType": ("s", True, ""),
            "biasesDataType": ("s", True, ""),
            "outputDataType": ("s", True, ""),
            # number of input vectors, examples:
            # [1] is a single vector (like a FC layer with batch=1)
            # [4] is four vectors (like a FC layer with batch=4)
            # [1, 4, 4] is four * four vectors (like a conv layer with batch=1)
            "numInputVectors": ("ints", False, [1]),
        }
        my_attrs.update(super().get_nodeattr_types())
        return my_attrs

    def make_shape_compatible_op(self, model):
        oshape = self.get_normal_output_shape()
        return super().make_const_shape_op(oshape)

    def infer_node_datatype(self, model):
        node = self.onnx_node
        idt = model.get_tensor_datatype(node.input[0])
        if idt != self.get_input_datatype():
            warn_str = "inputDataType changing for %s: %s -> %s " % (
                node.name,
                str(self.get_input_datatype().name),
                str(idt.name),
            )
            warnings.warn(warn_str)
        self.set_nodeattr("inputDataType", idt.name)
        # set output datatype from property
        odt = self.get_output_datatype()
        model.set_tensor_datatype(node.output[0], odt)

    def verify_node(self):
        info_messages = []
        # verify that "backend" is set to "fpgadataflow"
        backend_value = self.get_nodeattr("backend")
        if backend_value == "fpgadataflow":
            info_messages.append("Attribute backend is set correctly")
        else:
            info_messages.append('Attribute backend should be set to "fpgadataflow"')

        # verify that all necessary attributes exist
        # TODO collect automatically from get_nodeattr_types
        try:
            self.get_nodeattr("code_gen_dir_cppsim")
            self.get_nodeattr("executable_path")
            self.get_nodeattr("NumChannels")
            self.get_nodeattr("PE")
            self.get_nodeattr("inputDataType")
            self.get_nodeattr("outputDataType")
            info_messages.append("All necessary attributes exist")
        except Exception:
            info_messages.append("""The required POTLinearActivation attributes do not exist.""")

        return info_messages

    def get_input_datatype(self, ind=0):
        """Returns FINN DataType of input."""
        return DataType[self.get_nodeattr("inputDataType")]

    def get_output_datatype(self, ind=0):
        """Returns FINN DataType of output."""
        return DataType[self.get_nodeattr("outputDataType")]

    def get_shifts_datatype(self):
        """Returns FINN DataType of shifts."""
        return DataType[self.get_nodeattr("shiftsDataType")]

    def get_biases_datatype(self):
        """Returns FINN DataType of biases."""
        return DataType[self.get_nodeattr("biasesDataType")]

    # def get_weightstream_width(self):
    #     """Returns weight stream width"""
    #     pe = self.get_nodeattr("PE")
    #     wp = self.get_weight_datatype().bitwidth()
    #     n_thres_steps = self.get_nodeattr("numSteps")
    #     w_width = pe * wp * n_thres_steps
    #     return w_width

    def minimize_accumulator_width(self, model):
        "Minimize shifts and biases width ('accumulator width' here due to convention)"
        shifts = model.get_initializer(self.onnx_node.input[1])
        min_shifts = shifts.min()
        max_shifts = shifts.max()
        if min_shifts < 0:
            if abs(min_shifts) > max_shifts:
                sdt = DataType.get_smallest_possible(min_shifts)
            else:
                sdt = DataType.get_smallest_possible(-max_shifts - 1)
        else:
            sdt = DataType.get_smallest_possible(max_shifts)
        assert np.vectorize(sdt.allowed)(
            shifts
        ).all(), "Shifts can't be expressed with type %s" % str(sdt)
        self.set_nodeattr("shiftsDataType", sdt.name)
        # Update QONNX DataType of tensor for consistency
        model.set_tensor_datatype(self.onnx_node.input[1], sdt)

        biases = model.get_initializer(self.onnx_node.input[2])
        min_biases = biases.min()
        max_biases = biases.max()
        if min_biases < 0:
            if abs(min_biases) > max_biases:
                bdt = DataType.get_smallest_possible(min_biases)
            else:
                bdt = DataType.get_smallest_possible(-max_biases - 1)
        else:
            bdt = DataType.get_smallest_possible(-max_biases - 1)
        assert np.vectorize(bdt.allowed)(
            biases
        ).all(), "Biases can't be expressed with type %s" % str(bdt)
        self.set_nodeattr("biasesDataType", bdt.name)
        # Update QONNX DataType of tensor for consistency
        model.set_tensor_datatype(self.onnx_node.input[2], bdt)

    def get_instream_width(self, ind=0):
        i_bits = self.get_input_datatype().bitwidth()
        return i_bits * self.get_nodeattr("PE")

    def get_outstream_width(self, ind=0):
        o_bits = self.get_output_datatype().bitwidth()
        return o_bits * self.get_nodeattr("PE")

    def get_folded_input_shape(self, ind=0):
        pe = self.get_nodeattr("PE")
        ich = self.get_nodeattr("NumChannels")
        vecs = list(self.get_nodeattr("numInputVectors"))
        folded_input_shape = tuple(vecs + [ich // pe, pe])
        return folded_input_shape

    def get_folded_output_shape(self, ind=0):
        # same shape as input
        return self.get_folded_input_shape()

    def get_normal_input_shape(self, ind=0):
        ich = self.get_nodeattr("NumChannels")
        vecs = list(self.get_nodeattr("numInputVectors"))
        normal_input_shape = tuple(vecs + [ich])
        return normal_input_shape

    def get_normal_output_shape(self, ind=0):
        # same shape as input
        return self.get_normal_input_shape()

    def get_number_output_values(self):
        nf = np.prod(self.get_folded_output_shape()[:-1])
        return nf

    def get_exp_cycles(self):
        # Channels/PE * batch size * fmdim * fmdim
        return np.prod(self.get_folded_output_shape()[:-1])

    def execute_node(self, context, graph):
        node = self.onnx_node
        inp_values = context[node.input[0]]
        print("exec_node:")
        shifts = context[node.input[1]]
        biases = context[node.input[2]]
        y = np.trunc((inp_values + biases) * 2.0**shifts)
        odt = self.get_output_datatype()
        y = y.clip(odt.min(), odt.max())
        print(shifts)
        print(biases)
        print(y)
        context[node.output[0]] = y
