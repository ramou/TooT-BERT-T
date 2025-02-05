import warnings
warnings.filterwarnings("ignore")

import logging
logging.getLogger("transformers.modeling_utils").setLevel(logging.ERROR)

import re
import argparse
import joblib
from Bio import SeqIO
import torch
import numpy as np
from transformers import BertTokenizer, BertModel

device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')


parser = argparse.ArgumentParser(description="""A tool to classify transporter proteins using a BERT-based model.
Citation:
@InProceedings{10.1007/978-3-031-17024-9_1,
author="Ghazikhani, Hamed
and Butler, Gregory",
editor="Fdez-Riverola, Florentino
and Rocha, Miguel
and Mohamad, Mohd Saberi
and Caraiman, Simona
and Gil-Gonz{\'a}lez, Ana Bel{\'e}n",
title="TooT-BERT-T: A BERT Approach on Discriminating Transport Proteins from Non-transport Proteins",
booktitle="Practical Applications of Computational Biology and Bioinformatics, 16th International Conference (PACBB 2022)",
year="2023",
publisher="Springer International Publishing",
address="Cham",
pages="1--11",
abstract="Transmembrane transport proteins (transporters) serve a crucial role for the transport of hydrophilic molecules across hydrophobic membranes in every living cell. The structures and functions of many membrane proteins are unknown due to the enormous effort required to characterize them. This article proposes TooT-BERT-T, a technique that employs the BERT representation to analyze and discriminate between transporters and non-transporters using a Logistic Regression classifier. Additionally, we evaluate frozen and fine-tuned representations from two different BERT models. Compared to state-of-the-art prediction methods, TooT-BERT-T achieves the highest accuracy of 93.89{\%} and MCC of 0.86.",
isbn="978-3-031-17024-9"
}""")

parser.add_argument('input_file', type=str, help='Input FASTA file')
parser.add_argument('output_file', type=str, help='Output txt file with predicted labels')
parser.add_argument("-max_seq_len", help="maximum sequence length", type=int, default=20000)
parser.add_argument("-lr_model", help="path to the logistic regression model file", default="lr_model.pkl")
parser.add_argument('-tokenizer', type=str, default='rostlab/prot_bert_bfd', help='Specify the tokenizer to use. Refer to the Hugging Face model hub for available options.')
parser.add_argument("-problem_file", help="File to log problematic sequences", default="problem-sequences")

args = parser.parse_args()

# Set the default problem_file if not provided
if args.problem_file == "problem-sequences":
    args.problem_file = f"{args.output_file}.{args.problem_file}"

# We check if the input file is a fasta file. fasta file starts with > and then the id and then the sequence.
with open(args.input_file, 'r') as f:
    first_line = f.readline()
    if not first_line.startswith('>'):
        raise ValueError('Input file is not a fasta file.')

# Process the input file and write the output to output file.
with open(args.input_file, 'r') as f:
    # We read the input fasta file.
    records = list(SeqIO.parse(f, 'fasta'))
    # We create a list of sequences.
    sequences_ids = [(str(record.seq), str(record.id)) for record in records]

# We load the BERT model and the tokenizer.
print('Loading BERT model and tokenizer...')
tokenizer = BertTokenizer.from_pretrained(args.tokenizer, do_lower_case=False)
model = BertModel.from_pretrained('ghazikhanihamed/TransporterBERT')
model.to(device)

# We load the logistic regression model.
print('Loading logistic regression model...')
lr = joblib.load(args.lr_model)

# For each sequence, we tokenize it and then we pass it through the BERT model.
print("Sequence ID\t\tPredicted label")
print("------------\t\t---------------")
with open(args.output_file, 'w') as f, open(args.problem_file, 'w') as problem_file:
    for sequence, id in sequences_ids:
        try:

            # Make space between each amino acid.
            sequence = ' '.join(sequence)
            # Replace uncommon amino acids with X.
            sequence = re.sub('[UOBZ]', 'X', sequence)

            tokenized_sequence = tokenizer.encode_plus(sequence, add_special_tokens=True, max_length=args.max_seq_len, truncation=True)
            input_ids = torch.tensor([tokenized_sequence['input_ids']]).to(device)
            attention_mask = torch.tensor([tokenized_sequence['attention_mask']]).to(device)

            with torch.no_grad():
                last_hidden_states = model(input_ids, attention_mask=attention_mask)[0]

            embedding = last_hidden_states[0].cpu().numpy()

            seq_len = (attention_mask[0] == 1).sum()
            seq_embedding = embedding[1:seq_len-1]
            mean_pool = np.mean(seq_embedding, axis=0)

            # We predict the label.
            prediction = lr.predict([mean_pool])
            # We write the output to the output file.
            f.write(f"Sequence:{id}\tPrediction:{prediction[0]}\n")
            f.flush()

            # We print the id and the prediction.
            print(f"{id}\t{prediction[0]}")

        except Exception as e:
            problem_file.write(f"Problem with sequence {id}: {str(e)}\n")
            problem_file.flush()
            print(f"Problem with sequence {id}, skipping to the next one.")

print('Finished.')
