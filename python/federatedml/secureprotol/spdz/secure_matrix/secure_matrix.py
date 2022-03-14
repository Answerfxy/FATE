#
#  Copyright 2021 The FATE Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#


import numpy as np

from fate_arch.federation import Tag, get, remote
from fate_arch.session import PartiesInfo as Parties
from fate_arch.common import Party
from fate_arch.session import is_table
from federatedml.secureprotol.fixedpoint import FixedPointEndec
from federatedml.secureprotol.spdz.tensor import fixedpoint_numpy, fixedpoint_table
# from federatedml.transfer_variable.transfer_class.secret_share_transfer_variable import SecretShareTransferVariable
from federatedml.util import consts


class SecureMatrix(object):
    # SecureMatrix in SecretSharing With He;
    def __init__(self, party: Party, q_field, other_party):
        self.party = party
        self.other_party = other_party
        self.q_field = q_field
        self.encoder = None
        self.get_or_create_endec(self.q_field)

    def get_or_create_endec(self, q_field, **kwargs):
        if self.encoder is None:
            self.encoder = FixedPointEndec(q_field)
        return self.encoder

    @Tag("secure_matrix_mul")
    def secure_matrix_mul(self, matrix, tensor_name, cipher=None, is_fixedpoint_table=True):
        dst_parties = Parties.Guest[0] if self.party.role == consts.HOST else Parties.Host[0]

        if cipher is not None:
            de_matrix = self.encoder.decode(matrix.value)
            if isinstance(matrix, fixedpoint_table.FixedPointTensor):
                encrypt_mat = cipher.distribute_encrypt(de_matrix)
            else:
                encrypt_mat = cipher.recursive_encrypt(de_matrix)

            remote(parties=dst_parties, name=tensor_name, v=encrypt_mat)

            share_tensor = SecureMatrix.from_source(tensor_name,
                                                    self.other_party,
                                                    cipher,
                                                    self.q_field,
                                                    self.encoder,
                                                    is_fixedpoint_table=is_fixedpoint_table)

            return share_tensor

        else:
            share = get(parties=dst_parties, name=tensor_name)

            if is_table(share):
                share = fixedpoint_table.PaillierFixedPointTensor(share)

                ret = share.dot(matrix)
            else:
                share = fixedpoint_numpy.PaillierFixedPointTensor(share)
                ret = share.dot(matrix)

            share_tensor = SecureMatrix.from_source(tensor_name,
                                                    ret,
                                                    cipher,
                                                    self.q_field,
                                                    self.encoder)

            return share_tensor

    @Tag("share_encrypted_matrix")
    def share_encrypted_matrix(self, is_remote, cipher, **kwargs):
        dst_parties = Parties.Guest[0] if self.party.role == consts.HOST else Parties.Host[0]

        if is_remote:
            for var_name, var in kwargs.items():
                if isinstance(var, fixedpoint_table.FixedPointTensor):
                    encrypt_var = cipher.distribute_encrypt(var.value)
                else:
                    encrypt_var = cipher.recursive_encrypt(var.value)

                remote(parties=dst_parties, name=var_name, v=encrypt_var)
        else:
            res = []
            for var_name in kwargs.keys():
                z = get(parties=dst_parties, name=var_name)

                if is_table(z):
                    res.append(fixedpoint_table.PaillierFixedPointTensor(z))
                else:
                    res.append(fixedpoint_numpy.PaillierFixedPointTensor(z))

            return tuple(res)

    @classmethod
    def from_source(cls, tensor_name, source, cipher, q_field, encoder, is_fixedpoint_table=True):
        if is_table(source):
            share_tensor = fixedpoint_table.PaillierFixedPointTensor.from_source(tensor_name=tensor_name,
                                                                                 source=source,
                                                                                 encoder=encoder,
                                                                                 q_field=q_field)
            return share_tensor

        elif isinstance(source, np.ndarray):
            share_tensor = fixedpoint_numpy.PaillierFixedPointTensor.from_source(tensor_name=tensor_name,
                                                                                 source=source,
                                                                                 encoder=encoder,
                                                                                 q_field=q_field)
            return share_tensor

        elif isinstance(source, (fixedpoint_table.PaillierFixedPointTensor,
                                 fixedpoint_numpy.PaillierFixedPointTensor)):
            return cls.from_source(tensor_name, source.value, cipher, q_field, encoder, is_fixedpoint_table)

        elif isinstance(source, Party):
            if is_fixedpoint_table:
                share_tensor = fixedpoint_table.PaillierFixedPointTensor.from_source(tensor_name=tensor_name,
                                                                                     source=source,
                                                                                     encoder=encoder,
                                                                                     q_field=q_field,
                                                                                     cipher=cipher)
            else:
                share_tensor = fixedpoint_numpy.PaillierFixedPointTensor.from_source(tensor_name=tensor_name,
                                                                                     source=source,
                                                                                     encoder=encoder,
                                                                                     q_field=q_field,
                                                                                     cipher=cipher)

            return share_tensor
        else:
            raise ValueError(f"type={type(source)}")
