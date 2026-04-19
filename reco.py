function generateReport() {

            // ✅ Always use latest saved manual data
            const saved = sessionStorage.getItem("studentsData");

            if (saved) {
                students = JSON.parse(saved);
            }

            // ❌ If still empty → only then fetch from DB
            if (!students || students.length === 0) {

                const subjectId = sessionStorage.getItem("selectedSubjectId");

                if (!subjectId) {
                    alert("⚠️ No subject selected");
                    return;
                }

                fetch('/get-students', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                            subject_id: subjectId
                        })
                    })
                    .then(res => res.json())
                    .then(data => {
                        if (data.students) {
                            students = data.students.map(s => ({
                                roll: s.roll_no || s.student_id,
                                name: s.name,
                                contact: s.phone_No || s.phone || '-',
                                department: s.department || '-',
                                status: s.status || 'ABSENT',
                                reason: ''
                            }));

                            // ✅ Save it so next time no DB call
                            sessionStorage.setItem("studentsData", JSON.stringify(students));

                            renderReport();
                        }
                    });

            } else {
                // ✅ Directly render updated data
                renderReport();
            }
        }
        function renderReport() {
            const total = students.length;
            const present = students.filter(s => s.status === 'PRESENT').length;
            const absent = total - present;

            if (total === 0) {
                document.getElementById('present-percent').innerText = '0%';
                document.getElementById('absent-percent').innerText = '0%';
                return;
            }

            const presentPct = Math.round((present / total) * 100);
            const absentPct = 100 - presentPct;

            document.getElementById('present-percent').innerText = presentPct + '%';
            document.getElementById('absent-percent').innerText = absentPct + '%';

            // Animate rings
            const circumference = 2 * Math.PI * 60; // 377
            document.getElementById("present-ring").style.strokeDashoffset =
                circumference - (presentPct / 100) * circumference;
            document.getElementById("absent-ring").style.strokeDashoffset =
                circumference - (absentPct / 100) * circumference;

            // Absentees table
            const body = document.getElementById('absentees-body');
            let count = 1;
            body.innerHTML = students
                .filter(s => s.status === 'ABSENT')
                .map(s => `
        <tr class="border-b border-slate-50">
            <td class="py-3 font-semibold">${count++}</td>
            <td class="py-3 font-semibold">${s.name}</td>
            <td class="py-3 font-semibold">${s.roll}</td>
            <td class="py-3 font-semibold">${s.department}</td>
            <td class="py-3 font-semibold text-blue-500">${s.contact}</td>
        </tr>`).join('');
        }

        