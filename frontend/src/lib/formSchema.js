const opts = (a) => a.map((x) => ({ value: x, label: x }));
const STATES = ["Andhra Pradesh", "Assam", "Bihar", "Chhattisgarh", "Delhi", "Goa", "Gujarat", "Haryana", "Himachal Pradesh",
  "Jammu & Kashmir", "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra", "Odisha", "Punjab", "Rajasthan",
  "Tamil Nadu", "Telangana", "Uttar Pradesh", "Uttarakhand", "West Bengal", "Other"];
const school = (name, label) => ({ name, label, type: "group", fields: [
  { name: "board", label: "Board" }, { name: "school", label: "School / college" },
  { name: "year", label: "Year of passing", type: "number" }, { name: "percentage", label: "Percentage", type: "number" }] });

export const FORM_SCHEMA = {
  personal: [
    { name: "full_name", label: "Full name (as on marksheets)", wide: true },
    { name: "dob", label: "Date of birth", type: "date" },
    { name: "gender", label: "Gender", type: "select", options: opts(["Male", "Female", "Other"]) },
    { name: "category", label: "Category", type: "select", options: opts(["General", "OBC-NCL", "SC", "ST", "EWS"]) },
    { name: "nationality", label: "Nationality", type: "select", options: opts(["Indian", "NRI", "OCI", "Foreign National"]) },
    { name: "pwd", label: "Person with disability (PwD)", type: "switch" },
  ],
  family: [
    { name: "father_name", label: "Father's name" }, { name: "father_occupation", label: "Father's occupation" },
    { name: "mother_name", label: "Mother's name" }, { name: "mother_occupation", label: "Mother's occupation" },
    { name: "annual_family_income_inr", label: "Annual family income (INR)", type: "number" },
    { name: "siblings", label: "Siblings", type: "list", max: 6, itemLabel: "Sibling", fields: [
      { name: "name", label: "Name" }, { name: "relation", label: "Relation", type: "select", options: opts(["Brother", "Sister"]) },
      { name: "occupation", label: "Occupation" }] },
  ],
  contact: [
    { name: "address_line1", label: "Address line 1", wide: true }, { name: "address_line2", label: "Address line 2", wide: true },
    { name: "city", label: "City" }, { name: "state", label: "State", type: "select", options: opts(STATES) },
    { name: "pincode", label: "PIN code" }, { name: "alternate_mobile", label: "Alternate mobile (optional)" },
    { name: "emergency_contact_name", label: "Emergency contact name" }, { name: "emergency_contact_mobile", label: "Emergency contact mobile" },
  ],
  education: [
    school("class_x", "Class X"), school("class_xii", "Class XII"),
    { name: "graduation", label: "Graduation", type: "group", fields: [
      { name: "degree", label: "Degree (e.g. B.Com)" }, { name: "discipline", label: "Discipline" },
      { name: "university", label: "University", wide: true },
      { name: "status", label: "Status", type: "select", options: [{ value: "completed", label: "Completed" }, { value: "final_year", label: "Final year" }] },
      { name: "year", label: "Year of completion", type: "number" },
      { name: "score_type", label: "Score type", type: "select", options: [{ value: "percentage", label: "Percentage" }, { value: "cgpa", label: "CGPA (out of 10)" }] },
      { name: "score", label: "Score", type: "number" }] },
  ],
  work: [
    { name: "has_experience", label: "I have full-time work experience", type: "switch" },
    { name: "experiences", label: "Experience", type: "list", max: 8, itemLabel: "Experience", showIf: (v) => v.has_experience, fields: [
      { name: "organization", label: "Organisation" }, { name: "designation", label: "Designation" }, { name: "sector", label: "Sector" },
      { name: "start", label: "From", type: "month" }, { name: "end", label: "To (blank if current)", type: "month" }] },
  ],
  exams: [
    { name: "exams", label: "Exam", type: "list", min: 1, max: 7, itemLabel: "Exam", fields: [
      { name: "exam", label: "Exam", type: "select", options: opts(["CAT", "XAT", "CMAT", "GMAT", "MAH-CET", "NMAT", "ATMA"]) },
      { name: "year", label: "Year", type: "number" }, { name: "roll_number", label: "Roll / registration no." },
      { name: "status", label: "Status", type: "select", options: [{ value: "appeared", label: "Appeared (result out)" }, { value: "awaiting_result", label: "Awaiting result" }, { value: "registered", label: "Registered" }] },
      { name: "score", label: "Score (optional)", type: "number" }, { name: "percentile", label: "Percentile", type: "number" }] },
  ],
};

export const DEFAULTS = {
  personal: { pwd: false }, family: { siblings: [] }, contact: {}, education: { class_x: {}, class_xii: {}, graduation: {} },
  work: { has_experience: false, experiences: [] }, exams: { exams: [{}] }, preferences: { ranked: [] },
};
